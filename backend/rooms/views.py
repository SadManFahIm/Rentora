import django_filters
from django.db.models import Case, IntegerField, When
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from .geo import (
    BoundingBox,
    haversine_km,
    lat_delta_for_km,
    lng_delta_for_km,
)
from .landmarks import ALL_LANDMARKS, get_landmark
from .models import Room
from .permissions import IsOwnerOrReadOnly
from .serializers import (
    LandmarkSerializer,
    RoomCreateUpdateSerializer,
    RoomDetailSerializer,
    RoomListSerializer,
)


class RoomFilter(django_filters.FilterSet):
    price__gte = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    class Meta:
        model = Room
        fields = ["area", "room_type", "gender_preference", "is_available", "is_featured"]


# Query params that the geo layer consumes directly in `get_queryset`, rather
# than through `RoomFilter` — declared here only so they show up in the
# OpenAPI schema for the list endpoint.
_GEO_PARAMS = [
    OpenApiParameter(
        "bbox",
        str,
        description="Map viewport filter, GeoJSON order: `minLng,minLat,maxLng,maxLat`. "
        "Returns only rooms inside the box.",
    ),
    OpenApiParameter(
        "near_lat", float, description="Reference-point latitude (pair with near_lng)."
    ),
    OpenApiParameter(
        "near_lng", float, description="Reference-point longitude (pair with near_lat)."
    ),
    OpenApiParameter(
        "near_landmark",
        str,
        description="Landmark slug (e.g. `du`, `mrt_mirpur_10`) used as the reference point "
        "instead of near_lat/near_lng. See the /rooms/landmarks/ endpoint for valid slugs.",
    ),
    OpenApiParameter(
        "radius_km",
        float,
        description="With a reference point, keep only rooms within this many km of it.",
    ),
]


@extend_schema_view(
    list=extend_schema(
        tags=["Rooms"],
        summary="List rooms",
        description=(
            "Public, paginated room listing. Supports filtering by "
            "`area`, `room_type`, `gender_preference`, `is_available`, "
            "`is_featured`, and a `price__gte`/`price__lte` range; full-text "
            "`search` over title/description/area; and `ordering` by price, "
            "rating or created_at.\n\n"
            "**Geo/map queries:** `bbox` filters to a map viewport; a reference "
            "point (`near_lat`+`near_lng`, or `near_landmark`) with `radius_km` "
            "filters to rooms near a place, and — unless an explicit `ordering` "
            "is given — sorts them nearest-first and annotates each with "
            "`distance_km`."
        ),
        parameters=_GEO_PARAMS,
    ),
    retrieve=extend_schema(
        tags=["Rooms"],
        summary="Retrieve a room",
        description="Public room detail, including images, owner profile, and nearby landmarks.",
    ),
    create=extend_schema(
        tags=["Rooms"],
        summary="Create a room",
        description="Create a listing owned by the authenticated user. Landlord flow.",
        examples=[
            OpenApiExample(
                "Create room",
                value={
                    "title": "Sunny Studio in Dhanmondi",
                    "description": "Fully furnished studio with balcony.",
                    "room_type": "studio",
                    "price": "15000.00",
                    "area": "Dhanmondi",
                    "address": "Road 7, Dhanmondi, Dhaka",
                    "lat": "23.746000",
                    "lng": "90.376000",
                    "amenities": ["WiFi", "AC"],
                    "gender_preference": "any",
                    "size_sqft": 350,
                    "is_available": True,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(tags=["Rooms"], summary="Update a room (owner only)"),
    partial_update=extend_schema(tags=["Rooms"], summary="Partially update a room (owner only)"),
    destroy=extend_schema(tags=["Rooms"], summary="Delete a room (owner only)"),
)
class RoomViewSet(viewsets.ModelViewSet):
    """CRUD for room listings, plus geo/map query support.

    Reads (`list`/`retrieve`) are public; writes require authentication and,
    for an existing room, ownership (`IsOwnerOrReadOnly`).
    """

    queryset = Room.objects.select_related("owner").prefetch_related("images").all()
    filterset_class = RoomFilter
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    search_fields = ["title", "description", "area"]
    ordering_fields = ["price", "rating", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return RoomListSerializer
        if self.action == "retrieve":
            return RoomDetailSerializer
        return RoomCreateUpdateSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "landmarks"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # ----- geo query support ------------------------------------------------

    def _reference_point(self) -> tuple[float, float] | None:
        """Resolve the query's reference point from `near_landmark` (a slug)
        or an explicit `near_lat`/`near_lng` pair. Returns None if the request
        asked for neither; raises ValidationError on malformed input."""
        params = self.request.query_params

        landmark_key = params.get("near_landmark")
        if landmark_key:
            landmark = get_landmark(landmark_key)
            if landmark is None:
                raise ValidationError({"near_landmark": f"Unknown landmark '{landmark_key}'."})
            return (landmark.lat, landmark.lng)

        near_lat, near_lng = params.get("near_lat"), params.get("near_lng")
        if near_lat is None and near_lng is None:
            return None
        if near_lat is None or near_lng is None:
            raise ValidationError({"near_lat": "near_lat and near_lng must be supplied together."})
        try:
            return (float(near_lat), float(near_lng))
        except ValueError as exc:
            raise ValidationError({"near_lat": "near_lat/near_lng must be numbers."}) from exc

    def _apply_bbox(self, queryset):
        raw = self.request.query_params.get("bbox")
        if not raw:
            return queryset
        try:
            box = BoundingBox.parse(raw)
        except ValueError as exc:
            raise ValidationError({"bbox": str(exc)}) from exc
        return queryset.filter(
            lat__gte=box.min_lat,
            lat__lte=box.max_lat,
            lng__gte=box.min_lng,
            lng__lte=box.max_lng,
        )

    def _apply_radius(self, queryset, reference: tuple[float, float]):
        raw = self.request.query_params.get("radius_km")
        if not raw:
            return queryset
        try:
            radius = float(raw)
        except ValueError as exc:
            raise ValidationError({"radius_km": "radius_km must be a number."}) from exc
        if radius <= 0:
            raise ValidationError({"radius_km": "radius_km must be positive."})

        ref_lat, ref_lng = reference
        # Cheap indexable bounding-box pre-filter to discard far-away rows in
        # the DB, then an exact haversine refinement in Python on the small
        # survivor set — avoids a full-table trig scan (SQLite has no trig).
        d_lat = lat_delta_for_km(radius)
        d_lng = lng_delta_for_km(radius, ref_lat)
        prefiltered = queryset.filter(
            lat__gte=ref_lat - d_lat,
            lat__lte=ref_lat + d_lat,
            lng__gte=ref_lng - d_lng,
            lng__lte=ref_lng + d_lng,
        )
        # `.values()` (plain dicts) rather than `.only()` model instances —
        # the base queryset uses select_related("owner"), which can't coexist
        # with deferring columns on the same rows.
        matching_pks = [
            row["id"]
            for row in prefiltered.values("id", "lat", "lng")
            if haversine_km(ref_lat, ref_lng, float(row["lat"]), float(row["lng"])) <= radius
        ]
        return queryset.filter(pk__in=matching_pks)

    def _order_by_distance(self, queryset, reference: tuple[float, float]):
        """Order a (already geo-filtered, hence small) queryset nearest-first,
        preserving it as a queryset so pagination still works — the Python sort
        result is projected back via a Case/When on primary key."""
        ref_lat, ref_lng = reference
        ranked = sorted(
            queryset.values("id", "lat", "lng"),
            key=lambda row: haversine_km(ref_lat, ref_lng, float(row["lat"]), float(row["lng"])),
        )
        if not ranked:
            return queryset
        ordering = Case(
            *[When(pk=row["id"], then=position) for position, row in enumerate(ranked)],
            output_field=IntegerField(),
        )
        return queryset.filter(pk__in=[row["id"] for row in ranked]).order_by(ordering)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            return queryset

        queryset = self._apply_bbox(queryset)
        reference = self._reference_point()
        if reference is not None:
            queryset = self._apply_radius(queryset, reference)
        return queryset

    def filter_queryset(self, queryset):
        # Backends (django-filter, search, OrderingFilter's default
        # `-created_at`) run first; distance ordering is applied *after* so it
        # isn't clobbered. Nearest-first is the natural default for a "near X"
        # query, but an explicit ?ordering= (price, rating, …) must still win.
        queryset = super().filter_queryset(queryset)
        if self.action == "list" and not self.request.query_params.get("ordering"):
            reference = self._reference_point()
            if reference is not None:
                queryset = self._order_by_distance(queryset, reference)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Only meaningful on list, and only when a reference point was given —
        # lets the serializer emit `distance_km` for "X km away" rendering.
        if self.action == "list":
            try:
                context["reference_point"] = self._reference_point()
            except ValidationError:
                # A malformed reference point is surfaced by get_queryset as a
                # 400; don't also raise while building context.
                context["reference_point"] = None
        return context

    @extend_schema(
        tags=["Rooms"],
        summary="List map landmarks",
        description="Static set of universities and metro stations used for map layers and "
        "the `near_landmark` filter. Public, unpaginated.",
        responses=LandmarkSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def landmarks(self, request):
        return Response(LandmarkSerializer(ALL_LANDMARKS, many=True).data)
