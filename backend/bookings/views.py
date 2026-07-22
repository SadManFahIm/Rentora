from django.db.models import Q
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from .models import Booking, Review
from .permissions import IsReviewAuthorOrReadOnly, IsTenantOrRoomOwner
from .serializers import (
    BookingCreateSerializer,
    BookingSerializer,
    BookingUpdateSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=["Bookings"],
        summary="List my bookings",
        description="Bookings where the user is the tenant or owns the booked room.",
    ),
    retrieve=extend_schema(tags=["Bookings"], summary="Retrieve a booking"),
    create=extend_schema(
        tags=["Bookings"],
        summary="Request a booking",
        description="Tenant requests a booking; the room owner is notified.",
        examples=[
            OpenApiExample(
                "Booking request",
                value={"room": 1, "check_in": "2025-03-01", "notes": "Prefer early move-in."},
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Bookings"],
        summary="Update booking status",
        description=(
            "Owner approves/rejects a pending booking; tenant cancels a "
            "pending/approved booking. State transitions are validated."
        ),
    ),
    partial_update=extend_schema(tags=["Bookings"], summary="Partially update a booking"),
    destroy=extend_schema(tags=["Bookings"], summary="Delete a booking"),
)
class BookingViewSet(viewsets.ModelViewSet):
    """Bookings visible only to their tenant or the booked room's owner."""

    def get_queryset(self):
        # drf-spectacular introspects with an AnonymousUser; short-circuit so
        # schema generation doesn't run the user-scoped filter.
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        user = self.request.user
        return (
            Booking.objects.select_related("room", "room__owner", "tenant")
            .prefetch_related("room__images")
            .filter(Q(tenant=user) | Q(room__owner=user))
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        if self.action in ("update", "partial_update"):
            return BookingUpdateSerializer
        return BookingSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "retrieve"):
            return [permissions.IsAuthenticated(), IsTenantOrRoomOwner()]
        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        output = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        output = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(output.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Reviews"],
        summary="List reviews",
        description="Public review list. Filter by `room` to get one room's reviews.",
    ),
    retrieve=extend_schema(tags=["Reviews"], summary="Retrieve a review"),
    create=extend_schema(
        tags=["Reviews"],
        summary="Create a review",
        description=(
            "Authenticated users may review a room they hold an approved "
            "booking for (once). The room owner is notified."
        ),
        examples=[
            OpenApiExample(
                "Review",
                value={"room": 1, "rating": 5, "comment": "Great place, responsive owner."},
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(tags=["Reviews"], summary="Update a review (author only)"),
    partial_update=extend_schema(tags=["Reviews"], summary="Partially update a review (author only)"),
    destroy=extend_schema(tags=["Reviews"], summary="Delete a review (author only)"),
)
class ReviewViewSet(viewsets.ModelViewSet):
    """Room reviews. Reads are public; writing requires an approved booking."""

    queryset = Review.objects.select_related("user", "room").all()
    filterset_fields = ["room"]

    def get_serializer_class(self):
        if self.action == "create":
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsReviewAuthorOrReadOnly()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        output = ReviewSerializer(review, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)
