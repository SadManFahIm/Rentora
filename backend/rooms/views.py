import django_filters
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import permissions, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import Room
from .permissions import IsOwnerOrReadOnly
from .serializers import RoomCreateUpdateSerializer, RoomDetailSerializer, RoomListSerializer


class RoomFilter(django_filters.FilterSet):
    price__gte = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    class Meta:
        model = Room
        fields = ["area", "room_type", "gender_preference", "is_available", "is_featured"]


@extend_schema_view(
    list=extend_schema(
        tags=["Rooms"],
        summary="List rooms",
        description=(
            "Public, paginated room listing. Supports filtering by "
            "`area`, `room_type`, `gender_preference`, `is_available`, "
            "`is_featured`, and a `price__gte`/`price__lte` range; full-text "
            "`search` over title/description/area; and `ordering` by price, "
            "rating or created_at."
        ),
    ),
    retrieve=extend_schema(
        tags=["Rooms"],
        summary="Retrieve a room",
        description="Public room detail, including images and owner profile.",
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
    """CRUD for room listings.

    Reads (`list`/`retrieve`) are public; writes require authentication and,
    for an existing room, ownership (`IsOwnerOrReadOnly`).
    """

    queryset = Room.objects.select_related("owner").prefetch_related("images").all()
    filterset_class = RoomFilter
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend, SearchFilter, OrderingFilter]
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
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
