from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ModerationStatus, PhotoModeration, ReviewModeration
from .serializers import PhotoModerationSerializer, ReviewModerationSerializer

_QUEUE_CAP = 200


def _is_admin(user) -> bool:
    return user.is_staff or user.role == "admin"


def _queue_queryset(qs, request: Request):
    """Apply the ?status= filter (default: everything needing attention)."""
    status_filter = request.query_params.get("status", "attention")
    if status_filter == "attention":
        qs = qs.filter(status__in=[ModerationStatus.PENDING, ModerationStatus.FLAGGED])
    elif status_filter:
        qs = qs.filter(status=status_filter)
    return qs[:_QUEUE_CAP]


def _apply_decision(record, action: str, note: str, request: Request) -> None:
    """Approve/reject one moderation record + audit + notify the affected user."""
    if action == "approve":
        record.status = ModerationStatus.APPROVED
    elif action == "reject":
        record.status = ModerationStatus.REJECTED
    else:
        raise ValueError(action)

    record.admin_note = note
    record.reviewed_by = request.user
    record.reviewed_at = timezone.now()
    record.save()

    from audit.services import log_action
    from notifications.models import Notification
    from notifications.utils import create_notification

    kind = "review" if isinstance(record, ReviewModeration) else "photo"
    log_action(
        actor=request.user,
        action=f"moderation.{kind}.{action}",
        target=record,
        request=request,
        detail={
            "note": note,
            "risk_score": record.risk_score,
            "signals": [s.get("key") for s in record.signals],
        },
    )

    recipient = None
    action_url = "/dashboard"
    if isinstance(record, ReviewModeration):
        recipient = record.review.user
    elif record.uploaded_by_id:
        recipient = record.uploaded_by
    if recipient is not None:
        verb = "approved" if action == "approve" else "rejected"
        create_notification(
            user=recipient,
            notification_type=Notification.Type.CONTENT_MODERATED,
            title=f"Content {verb} by our team",
            message=note or f"One of your submissions was {verb} by our moderation team.",
            action_url=action_url,
        )


class ModerationOverviewView(APIView):
    """Admin dashboard counts across both moderation queues."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Moderation"],
        summary="Moderation overview counts",
        description="Admin only. Pending/flagged/approved/rejected counts for reviews and photos.",
        responses=inline_serializer(
            "ModerationOverviewResponse",
            fields={
                "reviews": serializers.IntegerField(),
                "reviews_pending": serializers.IntegerField(),
                "reviews_flagged": serializers.IntegerField(),
                "reviews_approved": serializers.IntegerField(),
                "reviews_rejected": serializers.IntegerField(),
                "photos": serializers.IntegerField(),
                "photos_pending": serializers.IntegerField(),
                "photos_flagged": serializers.IntegerField(),
                "photos_approved": serializers.IntegerField(),
                "photos_rejected": serializers.IntegerField(),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)

        def counts(qs) -> dict:
            return {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}

        reviews = counts(ReviewModeration.objects.all())
        photos = counts(PhotoModeration.objects.all())
        return Response(
            {
                "reviews": sum(reviews.values()),
                "reviews_pending": reviews.get(ModerationStatus.PENDING, 0),
                "reviews_flagged": reviews.get(ModerationStatus.FLAGGED, 0),
                "reviews_approved": reviews.get(ModerationStatus.APPROVED, 0),
                "reviews_rejected": reviews.get(ModerationStatus.REJECTED, 0),
                "photos": sum(photos.values()),
                "photos_pending": photos.get(ModerationStatus.PENDING, 0),
                "photos_flagged": photos.get(ModerationStatus.FLAGGED, 0),
                "photos_approved": photos.get(ModerationStatus.APPROVED, 0),
                "photos_rejected": photos.get(ModerationStatus.REJECTED, 0),
            }
        )


class ReviewModerationListView(APIView):
    """Admin review-moderation queue."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Moderation"],
        summary="List review moderation queue",
        description="Admin only. `?status=attention` (default) | pending | flagged | approved | rejected | all.",
        responses=ReviewModerationSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        qs = ReviewModeration.objects.select_related(
            "review", "review__room", "review__user", "reviewed_by"
        )
        return Response(ReviewModerationSerializer(_queue_queryset(qs, request), many=True).data)


class ReviewModerationDecisionView(APIView):
    """Admin decision on one review: approve | reject (audited + notified)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Moderation"],
        summary="Decide on a review",
        description="Admin only. `action`: approve | reject. Every decision is audited and the author is notified.",
        request=inline_serializer(
            "ModerationDecisionRequest",
            fields={
                "action": serializers.ChoiceField(choices=["approve", "reject"]),
                "note": serializers.CharField(required=False, allow_blank=True, default=""),
            },
        ),
        responses=ReviewModerationSerializer,
    )
    def post(self, request: Request, pk: int) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        record = (
            ReviewModeration.objects.select_related("review", "review__user").filter(pk=pk).first()
        )
        if record is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        action = (request.data.get("action") or "").lower()
        if action not in ("approve", "reject"):
            return Response(
                {"detail": "action must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _apply_decision(record, action, (request.data.get("note") or "").strip(), request)
        return Response(ReviewModerationSerializer(record).data)


class PhotoModerationListView(APIView):
    """Admin photo-moderation queue."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Moderation"],
        summary="List photo moderation queue",
        description="Admin only. `?status=attention` (default) | pending | flagged | approved | rejected | all.",
        responses=PhotoModerationSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        qs = PhotoModeration.objects.select_related("room", "review", "uploaded_by", "reviewed_by")
        return Response(PhotoModerationSerializer(_queue_queryset(qs, request), many=True).data)


class PhotoModerationDecisionView(APIView):
    """Admin decision on one photo: approve | reject (audited + notified)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Moderation"],
        summary="Decide on a photo",
        description="Admin only. `action`: approve | reject. Every decision is audited and the uploader is notified.",
        request=inline_serializer(
            "PhotoModerationDecisionRequest",
            fields={
                "action": serializers.ChoiceField(choices=["approve", "reject"]),
                "note": serializers.CharField(required=False, allow_blank=True, default=""),
            },
        ),
        responses=PhotoModerationSerializer,
    )
    def post(self, request: Request, pk: int) -> Response:
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        record = PhotoModeration.objects.select_related("uploaded_by").filter(pk=pk).first()
        if record is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        action = (request.data.get("action") or "").lower()
        if action not in ("approve", "reject"):
            return Response(
                {"detail": "action must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _apply_decision(record, action, (request.data.get("note") or "").strip(), request)
        return Response(PhotoModerationSerializer(record).data)
