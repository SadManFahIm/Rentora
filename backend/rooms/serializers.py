from django.contrib.auth import get_user_model
from rest_framework import serializers

from config.sanitizers import sanitize_text

from .models import Room, RoomImage

User = get_user_model()


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


class RoomListSerializer(serializers.ModelSerializer):
    """Representation used for room list/browse and anywhere a room summary is
    embedded (wishlist entries, bookings). Includes the fields the frontend
    card *and* detail modal render, so the list endpoint needs no follow-up
    detail fetch for the common views.
    """

    images = RoomImageSerializer(many=True, read_only=True)
    owner = RoomOwnerSerializer(read_only=True)

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
            "is_featured",
            "rating",
            "total_reviews",
            "verified",
            "owner",
            "images",
            "created_at",
        ]


class RoomDetailSerializer(serializers.ModelSerializer):
    """Full room representation, including nested images and owner profile."""

    images = RoomImageSerializer(many=True, read_only=True)
    owner = RoomOwnerSerializer(read_only=True)

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
            "is_featured",
            "owner",
            "rating",
            "total_reviews",
            "verified",
            "images",
            "created_at",
            "updated_at",
        ]


class RoomCreateUpdateSerializer(serializers.ModelSerializer):
    """Used for create/update. `owner` is set from the request in the view,
    not accepted from the client. Accepts a list of image files on write."""

    uploaded_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False
    )
    images = RoomImageSerializer(many=True, read_only=True)

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
            "is_featured",
            "images",
            "uploaded_images",
        ]

    def validate_title(self, value: str) -> str:
        """Strip any HTML from the title to prevent stored XSS."""
        return sanitize_text(value)

    def validate_description(self, value: str) -> str:
        """Strip any HTML from the free-text description (stored-XSS guard)."""
        return sanitize_text(value)

    def create(self, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
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
