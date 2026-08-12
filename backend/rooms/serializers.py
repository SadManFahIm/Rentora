from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from config.sanitizers import sanitize_text

from .geo import haversine_km, landmarks_within, nearest_landmark
from .landmarks import ALL_LANDMARKS, METRO_STATIONS, UNIVERSITIES, Landmark
from .models import Room, RoomImage

User = get_user_model()


class LandmarkSerializer(serializers.Serializer):
    """A single landmark (university or metro station) from the static
    reference set — used by the `/rooms/landmarks/` map-layer endpoint."""

    key = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.SerializerMethodField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()

    def get_kind(self, obj: Landmark) -> str:
        return obj.kind.value


def _nearby_payload(pair: tuple[Landmark, float] | None) -> dict | None:
    """Shape one (landmark, distance) result for API output, or None."""
    if pair is None:
        return None
    landmark, distance_km = pair
    return {
        "key": landmark.key,
        "name": landmark.name,
        "kind": landmark.kind.value,
        "distance_km": round(distance_km, 2),
    }


class RoomProximityMixin(serializers.Serializer):
    """Adds map/proximity fields shared by the list and detail representations.

    - `proximity`: the nearest university and nearest metro station to the
      room, each with its distance in km (or null if somehow no landmark
      exists). Computed in pure Python over the small static landmark set, so
      it adds no queries.
    - `distance_km`: distance from the *query's* reference point — populated
      only when the request carried one (`near_lat`/`near_lng` or
      `near_landmark`), so a client can render "2.3 km away". Null otherwise.
    """

    proximity = serializers.SerializerMethodField(
        help_text="Nearest university and metro station to this room, each with distance in km."
    )
    distance_km = serializers.SerializerMethodField(
        help_text="Distance (km) from the query's reference point; null unless the "
        "request supplied near_lat/near_lng or near_landmark."
    )

    def get_proximity(self, obj: Room) -> dict:
        lat, lng = float(obj.lat), float(obj.lng)
        return {
            "nearest_university": _nearby_payload(nearest_landmark(lat, lng, UNIVERSITIES)),
            "nearest_metro": _nearby_payload(nearest_landmark(lat, lng, METRO_STATIONS)),
        }

    def get_distance_km(self, obj: Room) -> float | None:
        reference = self.context.get("reference_point")
        if not reference:
            return None
        return round(haversine_km(reference[0], reference[1], float(obj.lat), float(obj.lng)), 2)


class RoomImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomImage
        fields = ["id", "image", "is_primary", "created_at"]
        read_only_fields = ["id", "created_at"]


class RoomOwnerSerializer(serializers.ModelSerializer):
    """Public-safe subset of the owner's profile, embedded in room responses."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "avatar", "phone", "nid_verified"]


class _EffectiveTierMixin(serializers.Serializer):
    """Expose the room's *effective* tier and featured flag.

    The viewset annotates `effective_tier` (free once `tier_expires_at`
    passes), so an expired promotion stops being reported as Premium/
    Featured — the paid benefit ends when the purchased period does.
    Falls back to the stored `tier` when the annotation is absent (e.g.
    room objects loaded outside the list viewset).
    """

    tier = serializers.SerializerMethodField()
    is_featured = serializers.SerializerMethodField()

    def get_tier(self, obj):
        effective = getattr(obj, "effective_tier", None)
        return effective or obj.tier

    @extend_schema_field(serializers.BooleanField())
    def get_is_featured(self, obj):
        return self.get_tier(obj) != "free"


class RoomListSerializer(_EffectiveTierMixin, RoomProximityMixin, serializers.ModelSerializer):
    """Representation used for room list/browse and anywhere a room summary is
    embedded (wishlist entries, bookings). Includes the fields the frontend
    card *and* detail modal render, so the list endpoint needs no follow-up
    detail fetch for the common views.
    """

    images = RoomImageSerializer(many=True, read_only=True)
    owner = RoomOwnerSerializer(read_only=True)
    amenities = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = Room
        fields = [
            "id",
            "title",
            "description",
            "room_type",
            "price",
            "area",
            "lat",
            "lng",
            "amenities",
            "gender_preference",
            "size_sqft",
            "is_available",
            "tier",
            "tier_expires_at",
            "is_featured",
            "rating",
            "total_reviews",
            "verified",
            "owner",
            "images",
            "proximity",
            "distance_km",
            "created_at",
        ]


class RoomDetailSerializer(_EffectiveTierMixin, RoomProximityMixin, serializers.ModelSerializer):
    """Full room representation, including nested images and owner profile."""

    images = RoomImageSerializer(many=True, read_only=True)
    owner = RoomOwnerSerializer(read_only=True)
    amenities = serializers.ListField(child=serializers.CharField(), required=False)
    price_insight = serializers.SerializerMethodField(
        help_text="How this room's price compares to its market segment; null if there "
        "isn't yet a big-enough market sample for its (area, room_type) to compare against."
    )
    nearby_landmarks = serializers.SerializerMethodField(
        help_text="All universities and metro stations within NEARBY_RADIUS_KM of the room, nearest first."
    )

    # Radius (km) used to populate `nearby_landmarks` on the detail view — a
    # short walk/rickshaw ride, the distance a tenant actually cares about.
    NEARBY_RADIUS_KM = 3.0

    class Meta:
        model = Room
        fields = [
            "id",
            "title",
            "description",
            "room_type",
            "price",
            "area",
            "address",
            "lat",
            "lng",
            "amenities",
            "gender_preference",
            "size_sqft",
            "is_available",
            "tier",
            "tier_expires_at",
            "is_featured",
            "owner",
            "rating",
            "total_reviews",
            "verified",
            "images",
            "price_insight",
            "proximity",
            "nearby_landmarks",
            "distance_km",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field({"type": "object", "nullable": True})
    def get_price_insight(self, obj):
        # Imported lazily so `rooms` never has to import `pricing` at module
        # load time — keeps `pricing` an optional, bolt-on concern rather
        # than a hard dependency of the rooms app.
        from pricing.serializers import PriceInsightSerializer
        from pricing.services.insight import get_price_insight

        insight = get_price_insight(obj)
        if insight is None:
            return None
        return PriceInsightSerializer(insight).data

    def get_nearby_landmarks(self, obj: Room) -> list[dict]:
        within = landmarks_within(
            float(obj.lat), float(obj.lng), self.NEARBY_RADIUS_KM, ALL_LANDMARKS
        )
        return [_nearby_payload(pair) for pair in within]


class RoomCreateUpdateSerializer(serializers.ModelSerializer):
    """Used for create/update. `owner` is set from the request in the view,
    not accepted from the client. Accepts a list of image files on write."""

    uploaded_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False
    )
    images = RoomImageSerializer(many=True, read_only=True)
    amenities = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = Room
        fields = [
            "id",
            "title",
            "description",
            "room_type",
            "price",
            "area",
            "address",
            "lat",
            "lng",
            "amenities",
            "gender_preference",
            "size_sqft",
            "is_available",
            "tier",
            "tier_expires_at",
            "is_featured",
            "images",
            "uploaded_images",
        ]
        read_only_fields = ["tier", "tier_expires_at", "is_featured"]

    def validate_title(self, value: str) -> str:
        """Strip any HTML from the title to prevent stored XSS."""
        return sanitize_text(value)

    def validate_description(self, value: str) -> str:
        """Strip any HTML from the free-text description (stored-XSS guard)."""
        return sanitize_text(value)

    def create(self, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        # A listing from an already-KYC-verified landlord starts verified
        # (``serializer.save(owner=...)`` puts the owner into validated_data).
        # The seed command uses ``Room.objects.create`` directly, so its
        # hand-tuned ``verified`` values are unaffected by this default.
        validated_data.setdefault("verified", validated_data["owner"].nid_verified)
        room = Room.objects.create(**validated_data)
        self._save_images(room, uploaded_images)
        return room

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        self._save_images(instance, uploaded_images)
        return instance

    def _save_images(self, room, uploaded_images):
        has_primary = room.images.filter(is_primary=True).exists()
        for i, image_file in enumerate(uploaded_images):
            RoomImage.objects.create(
                room=room,
                image=image_file,
                is_primary=(not has_primary and i == 0),
            )
