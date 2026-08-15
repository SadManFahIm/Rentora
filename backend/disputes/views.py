from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import parsers, permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking

from .models import Dispute, DisputeEvidence
from .serializers import (
    DisputeActionSerializer,
    DisputeCreateSerializer,
    DisputeEvidenceSerializer,
    DisputeSerializer,
)

_QUEUE_CAP = 200


def _is_admin(user) -> bool:
    return user.is_staff or user.role == "admin"


def _participant_or_admin(user, dispute: Dispute) -> bool:
    if _is_admin(user):
        return True
    booking = dispute.booking
    return user.pk in (booking.tenant_id, booking.room.owner_id)


def _notify_party(user, ntype, title, message, action_url="/dashboard"):
    from notifications.utils import create_notification

    create_notification(
        user=user, notification_type=ntype, title=title, message=message, action_url=action_url
    )


class DisputeListCreateView(APIView):
    """GET my disputes; POST open a dispute on an approved booking."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Disputes"],
        summary="List my disputes",
        description="Disputes where the user is the booking tenant, the room owner, or an admin.",
        responses=DisputeSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        user = request.user
        qs = Dispute.objects.select_related(
            "booking", "booking__room", "booking__room__owner", "booking__tenant", "opened_by"
        )
        if not _is_admin(user):
            qs = qs.filter(booking__tenant=user) | qs.filter(booking__room__owner=user)
            qs = qs.distinct()
        return Response(DisputeSerializer(qs[:_QUEUE_CAP], many=True).data)

    @extend_schema(
        tags=["Disputes"],
        summary="Open a dispute",
        description=(
            "A tenant or landlord may open ONE open dispute per approved booking "
            "(categories: deposit, property condition, cancellation, misrepresentation, "
            "payment, other). The other party is notified."
        ),
        request=DisputeCreateSerializer,
        responses=DisputeSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = (
            Booking.objects.select_related("room__owner", "tenant")
            .filter(pk=serializer.validated_data["booking"])
            .first()
        )
        if booking is None:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)
        user = request.user
        is_party = user.pk in (booking.tenant_id, booking.room.owner_id)
        if not is_party and not _is_admin(user):
            return Response(
                {"detail": "You are not a party to this booking."}, status=status.HTTP_403_FORBIDDEN
            )
        if booking.status != Booking.Status.APPROVED:
            return Response(
                {"detail": "Disputes can only be opened on approved bookings."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            Dispute.objects.filter(booking=booking, opened_by=user)
            .exclude(status__in=[Dispute.Status.RESOLVED, Dispute.Status.REJECTED])
            .exists()
        ):
            return Response(
                {"detail": "You already have an open dispute on this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dispute = Dispute.objects.create(
            booking=booking,
            opened_by=user,
            category=serializer.validated_data["category"],
            description=serializer.validated_data.get("description", ""),
        )
        other = booking.tenant if user.pk == booking.room.owner_id else booking.room.owner
        _notify_party(
            other,
            "dispute_opened",
            "A dispute was opened on a booking",
            f"{user.username} opened a {dispute.get_category_display()} dispute on your booking for {booking.room.title}.",
        )
        return Response(
            DisputeSerializer(dispute, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class DisputeDetailView(APIView):
    """GET one dispute (participant or admin) with its evidence."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Disputes"], summary="Dispute detail with evidence", responses=DisputeSerializer
    )
    def get(self, request: Request, pk: int) -> Response:
        dispute = (
            Dispute.objects.select_related(
                "booking", "booking__room", "booking__room__owner", "booking__tenant", "opened_by"
            )
            .prefetch_related("evidence")
            .filter(pk=pk)
            .first()
        )
        if dispute is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _participant_or_admin(request.user, dispute):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DisputeSerializer(dispute, context={"request": request}).data)


class DisputeEvidenceView(APIView):
    """POST evidence to a dispute (participant or admin)."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser]

    @extend_schema(
        tags=["Disputes"],
        summary="Add evidence",
        description="A text statement or an uploaded photo/document. Only the dispute's parties and admins can read it.",
        request=inline_serializer(
            "DisputeEvidenceRequest",
            fields={
                "kind": serializers.ChoiceField(
                    choices=["text", "photo", "document"], default="text"
                ),
                "content": serializers.CharField(required=False, allow_blank=True, default=""),
            },
        ),
        responses=DisputeEvidenceSerializer,
    )
    def post(self, request: Request, pk: int) -> Response:
        dispute = Dispute.objects.filter(pk=pk).first()
        if dispute is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _participant_or_admin(request.user, dispute):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if dispute.status in (Dispute.Status.RESOLVED, Dispute.Status.REJECTED):
            return Response(
                {"detail": "This dispute is closed and no longer accepts evidence."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        kind = request.data.get("kind", "text")
        if kind not in (
            DisputeEvidence.Kind.TEXT,
            DisputeEvidence.Kind.PHOTO,
            DisputeEvidence.Kind.DOCUMENT,
        ):
            return Response(
                {"detail": "kind must be text, photo or document."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        evidence = DisputeEvidence.objects.create(
            dispute=dispute,
            uploaded_by=request.user,
            kind=kind,
            content=(request.data.get("content") or "").strip(),
            file=request.FILES.get("file"),
        )
        other = (
            dispute.booking.tenant
            if request.user.pk == dispute.booking.room.owner_id
            else dispute.booking.room.owner
        )
        _notify_party(
            other,
            "dispute_update",
            "New evidence on a dispute",
            f"{request.user.username} added {evidence.get_kind_display()} evidence to dispute #{dispute.pk}.",
        )
        return Response(DisputeEvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED)


class DisputeAdminListView(APIView):
    """Admin queue of every dispute."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Disputes"],
        summary="List all disputes (admin)",
        description="Admin only. `?status=` filters (default: all open ones).",
        responses=DisputeSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        qs = Dispute.objects.select_related(
            "booking", "booking__room", "booking__room__owner", "booking__tenant", "opened_by"
        )
        status_filter = request.query_params.get("status", "open")
        if status_filter == "open":
            qs = qs.exclude(status__in=[Dispute.Status.RESOLVED, Dispute.Status.REJECTED])
        elif status_filter:
            qs = qs.filter(status=status_filter)
        return Response(DisputeSerializer(qs[:_QUEUE_CAP], many=True).data)


class DisputeAdminActionView(APIView):
    """Admin decision on a dispute: transition | resolve | reject (audited)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Disputes"],
        summary="Act on a dispute (admin)",
        description=(
            "transition (move status) | resolve (close with a decision; deposit decisions "
            "mark the booking deposit as released/refunded) | reject. Every action is audited."
        ),
        request=DisputeActionSerializer,
        responses=DisputeSerializer,
    )
    def post(self, request: Request, pk: int) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        dispute = (
            Dispute.objects.select_related(
                "booking", "booking__room", "booking__room__owner", "booking__tenant", "opened_by"
            )
            .filter(pk=pk)
            .first()
        )
        if dispute is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = DisputeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        resolution = (serializer.validated_data.get("resolution") or "").strip()

        with transaction.atomic():
            if action == "transition":
                dispute.status = serializer.validated_data["status"]
                dispute.save(update_fields=["status", "updated_at"])
            elif action == "resolve":
                decision = serializer.validated_data.get("decision", Dispute.Decision.NONE)
                if decision == Dispute.Decision.NONE and not resolution:
                    return Response(
                        {"detail": "resolve requires a decision or a resolution note."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                dispute.status = Dispute.Status.RESOLVED
                dispute.decision = decision
                dispute.decision_amount = serializer.validated_data.get("decision_amount")
                dispute.resolution = resolution
                dispute.resolved_by = request.user
                dispute.resolved_at = timezone.now()
                dispute.save()
                # Deposit outcome: any decided dispute means the deposit is no
                # longer held by the platform — record that it was released or
                # refunded (the decision records who received it).
                if decision in (
                    Dispute.Decision.RELEASE_TO_LANDLORD,
                    Dispute.Decision.REFUND_TO_TENANT,
                    Dispute.Decision.PARTIAL_RESOLUTION,
                ):
                    booking = dispute.booking
                    booking.security_deposit_refunded = True
                    booking.save(update_fields=["security_deposit_refunded", "updated_at"])
            else:  # reject
                dispute.status = Dispute.Status.REJECTED
                dispute.resolution = resolution
                dispute.resolved_by = request.user
                dispute.resolved_at = timezone.now()
                dispute.save()

            from audit.services import log_action

            log_action(
                actor=request.user,
                action=f"dispute.{action}",
                target=dispute,
                request=request,
                detail={
                    "dispute_id": dispute.pk,
                    "booking_id": dispute.booking_id,
                    "category": dispute.category,
                    "status": dispute.status,
                    "decision": dispute.decision,
                    "resolution": resolution,
                },
            )

        # Notify both parties of the state change.
        from notifications.models import Notification

        for party in (dispute.booking.tenant, dispute.booking.room.owner):
            if party.pk == request.user.pk:
                continue
            _notify_party(
                party,
                Notification.Type.DISPUTE_UPDATE,
                "Dispute updated",
                f"Dispute #{dispute.pk} is now {dispute.get_status_display()}.",
            )

        return Response(DisputeSerializer(dispute, context={"request": request}).data)
