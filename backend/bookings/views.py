from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from moderation.models import NOT_PUBLIC
from moderation.services import record_review_moderation, record_review_photo_moderation

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
        if self.action in ("update", "partial_update", "destroy", "retrieve", "deposit_status"):
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

    @extend_schema(
        tags=["Bookings"],
        summary="Security deposit status (owner or tenant)",
        description="Whether a deposit is required for this booking, and its paid/refunded state.",
    )
    @action(detail=True, methods=["get"], url_path="deposit-status")
    def deposit_status(self, request, pk=None):
        booking = self.get_object()
        required = bool(getattr(settings, "REQUIRE_SECURITY_DEPOSIT_BEFORE_APPROVAL", False)) and (
            booking.security_deposit_amount > 0
        )
        return Response(
            {
                "booking_id": booking.id,
                "security_deposit_amount": float(booking.security_deposit_amount),
                "security_deposit_paid": booking.security_deposit_paid,
                "security_deposit_refunded": booking.security_deposit_refunded,
                "required_before_approval": required,
            }
        )


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
    partial_update=extend_schema(
        tags=["Reviews"], summary="Partially update a review (author only)"
    ),
    destroy=extend_schema(tags=["Reviews"], summary="Delete a review (author only)"),
)
class ReviewViewSet(viewsets.ModelViewSet):
    """Room reviews. Reads are public; writing requires an approved booking.

    Phase 12.5 — content moderation: every review is assessed on creation.
    Reviews held in moderation (``pending``/``flagged``/``rejected``) are
    withheld from the public list until an admin approves them; auto-approved
    low-risk reviews publish immediately, preserving the pre-moderation UX.
    """

    queryset = Review.objects.select_related("user", "room").all()
    filterset_fields = ["room"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Review.objects.none()
        return super().get_queryset().exclude(moderation__status__in=list(NOT_PUBLIC))

    def get_serializer_class(self):
        if self.action == "create":
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "summary"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        if self.action == "reply":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsReviewAuthorOrReadOnly()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        # Phase 12.5 — content moderation: assess the text + any review photos.
        # Auto-approves low-risk reviews; high-risk ones go to the admin queue.
        record_review_moderation(review)
        for url in review.photos or []:
            record_review_photo_moderation(review, url, request.user)
        output = ReviewSerializer(review, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Reviews"],
        summary="Rating breakdown for a room",
        description=(
            "Aggregated rating stats for one room: average, total, counts "
            "per star and the recent reviews (with any landlord replies)."
        ),
        responses=inline_serializer(
            "ReviewSummaryResponse",
            fields={
                "room": serializers.IntegerField(),
                "average_rating": serializers.FloatField(),
                "total_reviews": serializers.IntegerField(),
                "counts_per_star": serializers.DictField(child=serializers.IntegerField()),
                "recent": ReviewSerializer(many=True),
                "ai_summary": serializers.DictField(),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Rating breakdown + recent reviews for ``?room=<id>``, plus an
        automatic AI summary (Phase 15, C5): a Bengali statistical summary,
        the sentiment distribution and the most-discussed topics."""
        room_id = request.query_params.get("room")
        if not room_id:
            return Response(
                {"detail": "room query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reviews = self.get_queryset().filter(room_id=room_id)
        from django.db.models import Avg, Count

        agg = reviews.aggregate(avg=Avg("rating"), total=Count("id"))
        per_star = {str(star): reviews.filter(rating=star).count() for star in range(1, 6)}
        recent = ReviewSerializer(
            reviews[:10], many=True, context=self.get_serializer_context()
        ).data

        from .review_summary import analyze_reviews

        ai_summary = analyze_reviews(reviews)
        return Response(
            {
                "room": int(room_id),
                "average_rating": round(float(agg["avg"] or 0), 2),
                "total_reviews": agg["total"],
                "counts_per_star": per_star,
                "recent": recent,
                "ai_summary": ai_summary,
            }
        )

    @extend_schema(
        tags=["Reviews"],
        summary="Landlord reply to a review",
        description=(
            "The room owner (or an admin) answers a review. One reply per "
            "review — replying again overwrites the earlier text and timestamp."
        ),
        request=inline_serializer(
            "ReviewReplyRequest",
            fields={"reply": serializers.CharField()},
        ),
        responses=inline_serializer(
            "ReviewReplyResponse",
            fields={"status": serializers.CharField(), "reply": serializers.CharField()},
        ),
    )
    @action(detail=True, methods=["post"], url_path="reply")
    def reply(self, request, pk=None):
        """Room owner / admin sets the landlord reply on a review."""
        from django.utils import timezone

        review = self.get_object()
        is_staff = request.user.is_staff or request.user.role == request.user.Role.ADMIN
        if not is_staff and review.room.owner_id != request.user.id:
            return Response(
                {"detail": "Only the room owner can reply."},
                status=status.HTTP_403_FORBIDDEN,
            )
        text = (request.data.get("reply") or "").strip()
        if not text:
            return Response(
                {"detail": "reply is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        review.reply = text[:2000]
        review.replied_at = timezone.now()
        review.save(update_fields=["reply", "replied_at"])
        return Response({"status": "ok", "reply": review.reply})
