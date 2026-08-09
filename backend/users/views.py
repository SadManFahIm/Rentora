from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.emails import send_html_email
from notifications.utils import create_notification

from .models import KycDocument, User
from .serializers import (
    KycAuditEntrySerializer,
    KycDocumentSerializer,
    KycPendingUserSerializer,
    KycReviewRequestSerializer,
    KycSlaSerializer,
    KycUploadRequestSerializer,
    UserSerializer,
)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only user directory. Staff see everyone; regular users see only themselves."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return User.objects.all().order_by("id")
        return User.objects.filter(pk=user.pk)


# ============================================================
# KYC verification — document upload + admin review panel
# ============================================================


def _is_admin(user: User) -> bool:
    """Django staff or the app-level admin role — mirrors the fraud views' check."""
    return user.is_staff or user.role == User.Role.ADMIN


# Server-side guardrails for uploaded KYC proofs. Kept module-level so the
# POST handler and (optionally) tests share them.
MAX_KYC_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_KYC_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

# Review-SLA breach thresholds — shared by the SLA endpoint (flags) and the
# beat task (alerts), so the dashboard and the alerts never disagree.
# An application older than this (hours) is considered a breach.
SLA_OLDEST_PENDING_BREACH_H = 48.0


class KycDocumentFileView(APIView):
    """Serve one KYC document's bytes — owner or admin only.

    Documents are deliberately NOT served from the public MEDIA_URL (Django's
    dev server would serve those to anyone). This authenticated endpoint is
    what the serializers point at, so the privacy contract holds even in
    DEBUG. Non-owners get a 404 (not 403) so a guessed document id doesn't
    even confirm a document exists.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["KYC"],
        summary="Download a KYC document",
        description="Authenticated. Owner or admin only; otherwise 404.",
    )
    def get(self, request, document_id):
        document = get_object_or_404(KycDocument, pk=document_id)
        if not (_is_admin(request.user) or document.user_id == request.user.id):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(document.file.open("rb"))
        response["Content-Disposition"] = f'inline; filename="{document.file.name}"'
        return response


class KycDocumentListCreateView(APIView):
    """Upload a KYC document, or list KYC documents.

    - ``GET`` — the caller's own documents; staff see everyone's.
    - ``POST`` — upload a document for the caller (multipart form).
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @extend_schema(
        tags=["KYC"],
        summary="List my KYC documents",
        description="The caller's own submitted documents (staff see all users'). "
        "Never exposed publicly.",
        responses=KycDocumentSerializer(many=True),
    )
    def get(self, request):
        queryset = (
            KycDocument.objects.all()
            if _is_admin(request.user)
            else KycDocument.objects.filter(user=request.user)
        )
        return Response(
            KycDocumentSerializer(
                queryset.select_related("user"), many=True, context={"request": request}
            ).data
        )

    @extend_schema(
        tags=["KYC"],
        summary="Upload a KYC document",
        description="Multipart: `doc_type` (nid|passport) + `file` (image or PDF, up to 5 MB).",
        request=KycUploadRequestSerializer,
        responses=KycDocumentSerializer,
    )
    def post(self, request):
        doc_type = request.data.get("doc_type")
        file_obj = request.data.get("file")
        if doc_type not in KycDocument.DocType.values:
            return Response(
                {"doc_type": "doc_type must be one of: nid, passport."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file_obj is None:
            return Response(
                {"file": "A document file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = getattr(file_obj, "content_type", "")
        if content_type and content_type not in ALLOWED_KYC_CONTENT_TYPES:
            return Response(
                {"file": "Only JPG, PNG, WebP images or PDF documents are accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file_obj.size > MAX_KYC_FILE_SIZE:
            return Response(
                {"file": "The document must be 5 MB or smaller."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        document = KycDocument.objects.create(user=request.user, doc_type=doc_type, file=file_obj)
        return Response(
            KycDocumentSerializer(document, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class KycPendingApplicationsView(APIView):
    """Admin review queue: users with pending KYC documents."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["KYC"],
        summary="List pending KYC applications",
        description="Admin only. Users with at least one pending document, newest first, "
        "each with their documents attached.",
        responses=KycPendingUserSerializer(many=True),
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        users_with_pending = (
            User.objects.filter(kyc_documents__status=KycDocument.Status.PENDING)
            .distinct()
            .order_by("-date_joined")
        )
        return Response(
            KycPendingUserSerializer(
                users_with_pending.prefetch_related("kyc_documents"),
                many=True,
                context={"request": request},
            ).data
        )


class KycSlaStatsView(APIView):
    """Admin-only review-queue health: pending volume, decision speed, trend.

    Powers the SLA card on the admin KYC panel. All times are computed from
    the documents themselves (``created_at`` → ``reviewed_at``), so the
    numbers reflect the real review workload, not the audit log.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["KYC"],
        summary="KYC review SLA stats",
        description="Admin only. Pending count, average review time (hours), "
        "7-day decision trend and oldest pending document age.",
        responses=KycSlaSerializer,
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from datetime import timedelta

        from django.db.models import Avg, DurationField, ExpressionWrapper, F

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        resolved = KycDocument.objects.exclude(reviewed_at=None)
        review_time = ExpressionWrapper(
            F("reviewed_at") - F("created_at"), output_field=DurationField()
        )

        def avg_hours(qs):
            agg = qs.aggregate(avg=Avg(review_time))
            if agg["avg"] is None:
                return None
            return round(agg["avg"].total_seconds() / 3600, 1)

        resolved_count = resolved.count()
        last_7d_decisions = resolved.filter(reviewed_at__gte=week_ago).count()
        prev_7d_decisions = resolved.filter(
            reviewed_at__gte=two_weeks_ago, reviewed_at__lt=week_ago
        ).count()

        oldest_pending = (
            KycDocument.objects.filter(status=KycDocument.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        pending_oldest_hours = None
        if oldest_pending:
            pending_oldest_hours = round(
                (now - oldest_pending.created_at).total_seconds() / 3600, 1
            )

        # ---- Breach flags (share the thresholds with the beat task) ----
        breaches = []
        if pending_oldest_hours is not None and pending_oldest_hours > SLA_OLDEST_PENDING_BREACH_H:
            breaches.append("oldest_pending")
        if last_7d_decisions - prev_7d_decisions < 0:
            breaches.append("trend_negative")

        # ---- Last-30-days trend: daily decisions + avg review hours ----
        # TruncDate (not ExpressionWrapper) so the bucket key is a real date
        # on SQLite *and* Postgres.
        from django.db.models import Count
        from django.db.models.functions import TruncDate

        trend_start = now - timedelta(days=29)
        daily = (
            resolved.filter(reviewed_at__gte=trend_start)
            .annotate(day=TruncDate("reviewed_at"))
            .values("day")
            .annotate(
                decisions=Count("id"),
                avg=Avg(review_time),
            )
            .order_by("day")
        )
        by_day = {}
        for row in daily:
            avg_h = None
            if row["avg"] is not None:
                avg_h = round(row["avg"].total_seconds() / 3600, 1)
            by_day[row["day"]] = {"decisions": row["decisions"], "avg_review_hours": avg_h}
        trend_30d = []
        for i in range(30):  # oldest first, today last
            day = (trend_start + timedelta(days=i)).date()
            trend_30d.append(
                {
                    "date": day.isoformat(),
                    **by_day.get(day, {"decisions": 0, "avg_review_hours": None}),
                }
            )

        data = {
            "pending_count": KycDocument.objects.filter(status=KycDocument.Status.PENDING).count(),
            "resolved_count": resolved_count,
            "avg_review_hours": avg_hours(resolved),
            "last_7d_decisions": last_7d_decisions,
            "last_7d_avg_review_hours": avg_hours(resolved.filter(reviewed_at__gte=week_ago)),
            "prev_7d_decisions": prev_7d_decisions,
            "decision_delta_7d": last_7d_decisions - prev_7d_decisions,
            "pending_oldest_hours": pending_oldest_hours,
            "breaches": breaches,
            "trend_30d": trend_30d,
        }
        return Response(KycSlaSerializer(data).data)


class KycAuditTrailView(APIView):
    """Admin-only KYC decision history — the approve/reject timeline.

    Reads the append-only audit log (``AuditLogEntry``, action prefix
    ``kyc.``), so the trail shows exactly what was decided, by whom, when,
    and with which note — and cannot be rewritten.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["KYC"],
        summary="KYC decision history",
        description="Admin only. Newest first, at most 50 entries: who decided, on "
        "whom, when, and with what note.",
        responses=KycAuditEntrySerializer(many=True),
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from audit.models import AuditLogEntry

        entries = list(
            AuditLogEntry.objects.filter(action__startswith="kyc.")
            .select_related("actor")
            .order_by("-created_at")[:50]
        )
        user_ids = [int(e.target_id) for e in entries if e.target_id.isdigit()]
        users = {u.id: u for u in User.objects.filter(id__in=user_ids)}

        data = []
        for entry in entries:
            actor = entry.actor
            target = users.get(int(entry.target_id)) if entry.target_id.isdigit() else None
            data.append(
                {
                    "id": entry.id,
                    "action": entry.action,
                    "actor_username": actor.username if actor else "System",
                    "actor_name": (actor.get_full_name() or actor.username) if actor else "System",
                    "user_id": target.id if target else None,
                    "user_name": (target.get_full_name() or target.username)
                    if target
                    else entry.target_id,
                    "note": (entry.detail or {}).get("note", ""),
                    "created_at": entry.created_at,
                }
            )
        return Response(data)


class KycReviewView(APIView):
    """Admin decision on a user's KYC: approve flips ``nid_verified`` on
    (which the users signals propagate to every listing badge); reject clears
    it (revoking an existing verification). Pending documents are marked
    accordingly with the reviewer's note, and everything is audited.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["KYC"],
        summary="Review a KYC application",
        description="Admin only. `approved: true` marks the user verified; `false` "
        "revokes/keeps unverified. Pending documents are resolved and an audit "
        "entry + notification are created.",
        request=KycReviewRequestSerializer,
        responses=KycPendingUserSerializer,
    )
    def post(self, request, user_id):
        if not _is_admin(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = KycReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target = get_object_or_404(User, pk=user_id)
        approved = serializer.validated_data["approved"]
        note = serializer.validated_data.get("note", "")

        # The decision is all-or-nothing: if any step fails, the user's KYC
        # state must not change while documents stay pending — a state no one
        # could reconcile.
        from django.db import transaction

        with transaction.atomic():
            target.nid_verified = approved
            # instance.save(): fires the badge-sync signal on nid_verified.
            target.save(update_fields=["nid_verified"])

            # Resolve every still-pending document for this user in one go.
            pending = KycDocument.objects.filter(user=target, status=KycDocument.Status.PENDING)
            pending.update(
                status=(KycDocument.Status.APPROVED if approved else KycDocument.Status.REJECTED),
                review_note=note,
                reviewed_at=timezone.now(),
            )

            from audit.services import log_action

            log_action(
                actor=request.user,
                action=f"kyc.{'approved' if approved else 'rejected'}",
                target=target,
                request=request,
                detail={"note": note, "documents": list(pending.values_list("id", flat=True))},
            )
            create_notification(
                user=target,
                notification_type="kyc_" + ("approved" if approved else "rejected"),
                title=("KYC verified 🎉" if approved else "KYC document not approved"),
                message=(
                    "Your identity documents were approved. Your listings now show the verified badge."
                    if approved
                    else (
                        note
                        or "Your identity document could not be verified. "
                        "Please re-upload a clear copy."
                    )
                ),
                action_url="/dashboard",
            )

            # Rejection gets a branded email with the reviewer's note and a
            # direct re-upload link, so the landlord can fix and resubmit
            # without hunting through the app. Sent only *after* the decision
            # commits (on_commit): an SMTP hiccup must never hold the DB
            # transaction open, and a rolled-back decision must never mail a
            # landlord about an approval that didn't happen.
            if not approved:
                transaction.on_commit(
                    lambda: send_html_email(
                        subject="Your Rentora identity verification needs attention",
                        to_email=target.email,
                        template_name="kyc_rejected",
                        context={
                            "user": target,
                            "note": note,
                            "action_url": f"{settings.FRONTEND_URL}/dashboard?tab=kyc",
                        },
                    )
                )
        return Response(KycPendingUserSerializer(target, context={"request": request}).data)
