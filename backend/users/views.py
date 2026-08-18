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
from notifications.models import Notification
from notifications.utils import create_notification

from .models import KycDocument, TenantVerification, User
from .serializers import (
    KycAuditEntrySerializer,
    KycDocumentSerializer,
    KycPendingUserSerializer,
    KycReviewRequestSerializer,
    KycSlaSerializer,
    KycUploadRequestSerializer,
    TenantKycPendingSerializer,
    TenantKycReviewRequestSerializer,
    TenantVerificationSerializer,
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


# ============================================================
# Tenant KYC verification (Phase 12 — two-sided trust)
# ============================================================


# How long an approved tenant verification stays valid before expiring.
# Identity documents age; a verified badge should never be a lifetime claim.
TENANT_KYC_EXPIRY_DAYS = 365


class TenantKycView(APIView):
    """The tenant's own verification: read status or submit a document.

    - ``GET`` — the caller's verification record (null when never started).
      A verified record past ``expires_at`` is lazily flipped to EXPIRED and
      clears ``tenant_verified``, so a stale badge can't outlive its proof.
    - ``POST`` — submit (or re-submit) an identity document. Re-submission is
      allowed from rejected/expired/needs_review, blocked while pending and
      once verified. Files are validated (type + size + non-empty) and renamed
      to a UUID so original filenames never leak NID data into storage/logs.
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @extend_schema(
        tags=["Tenant KYC"],
        summary="My tenant verification status",
        description="Authenticated. The caller's own tenant-verification record, "
        "or null when not started. Document URL is owner-only.",
        responses=TenantVerificationSerializer,
    )
    def get(self, request):
        verification = TenantVerification.objects.filter(user=request.user).first()
        if verification is not None:
            self._expire_if_stale(verification)
        return Response(
            TenantVerificationSerializer(verification, context={"request": request}).data
            if verification
            else None
        )

    @extend_schema(
        tags=["Tenant KYC"],
        summary="Submit a tenant identity document",
        description="Multipart: `doc_type` (nid|passport) + `file` (image or PDF, up to 5 MB). "
        "Re-submission allowed after rejection/expiry/needs-review.",
        request=KycUploadRequestSerializer,
        responses=TenantVerificationSerializer,
    )
    def post(self, request):
        # Guard on both the cached user flag and the authoritative record: the
        # flag can be stale on a long-lived request object, and the record's
        # VERIFIED status is what actually gates resubmission.
        verification = TenantVerification.objects.filter(user=request.user).first()
        if request.user.tenant_verified or (
            verification is not None and verification.status == TenantVerification.Status.VERIFIED
        ):
            return Response(
                {"detail": "You are already verified as a tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if verification is not None and verification.status == TenantVerification.Status.PENDING:
            return Response(
                {"detail": "Your verification is already under review."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        if file_obj.size <= 0:
            return Response(
                {"file": "The document appears to be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verification, _created = TenantVerification.objects.get_or_create(user=request.user)

        # UUID-rename the upload so the original filename (which often embeds
        # an NID number) never reaches storage, logs, or error reporting.
        import os
        import uuid

        ext = os.path.splitext(getattr(file_obj, "name", ""))[1].lower()[:10]
        file_obj.name = f"{uuid.uuid4().hex}{ext}"

        verification.doc_type = doc_type
        verification.file = file_obj
        verification.status = TenantVerification.Status.PENDING
        verification.review_note = ""
        verification.reviewed_at = None
        verification.expires_at = None
        verification.save()

        # Automated pre-screening (Tier 2): score the submission and record
        # the recommendation + reasons for the admin queue. It never decides
        # alone — the admin still reviews every application.
        from .kyc_auto import auto_screen

        screen = auto_screen(verification)
        verification.auto_screen_score = screen["score"]
        verification.auto_screen_result = screen["result"]
        verification.auto_screen_detail = {"reasons": screen["reasons"]}
        verification.save(
            update_fields=["auto_screen_score", "auto_screen_result", "auto_screen_detail"]
        )

        from audit.services import log_action

        log_action(
            actor=request.user,
            action="tenant_kyc.submitted",
            target=request.user,
            request=request,
            detail={"doc_type": doc_type, "verification_id": verification.pk},
        )

        # Automated verification provider (Tier 4): when enabled, a provider
        # may auto-approve at high confidence — still audited, still
        # overridable by the admin queue. Off by default (safe rollout).
        from .kyc_provider import run_provider

        provider_result = run_provider(verification)
        if provider_result is not None and provider_result.approved:
            from datetime import timedelta

            from django.conf import settings

            if provider_result.confidence >= float(
                getattr(settings, "KYC_AUTO_APPROVE_MIN_CONFIDENCE", 0.7)
            ):
                verification.status = TenantVerification.Status.VERIFIED
                verification.review_note = (
                    f"Auto-approved by {provider_result.provider} provider "
                    f"(confidence {provider_result.confidence:.0%})."
                )
                verification.reviewed_at = timezone.now()
                verification.expires_at = timezone.now() + timedelta(
                    days=getattr(settings, "KYC_VALIDITY_DAYS", 365)
                )
                verification.save(
                    update_fields=[
                        "status",
                        "review_note",
                        "reviewed_at",
                        "expires_at",
                        "updated_at",
                    ]
                )
                request.user.tenant_verified = True
                request.user.save(update_fields=["tenant_verified"])
                log_action(
                    actor=request.user,
                    action="tenant_kyc.auto_approved",
                    target=request.user,
                    request=request,
                    detail={
                        "provider": provider_result.provider,
                        "confidence": provider_result.confidence,
                        "verification_id": verification.pk,
                    },
                )

        return Response(
            TenantVerificationSerializer(verification, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def _expire_if_stale(self, verification: TenantVerification) -> None:
        """Lazily expire a verified record past its validity window."""
        if (
            verification.status == TenantVerification.Status.VERIFIED
            and verification.expires_at
            and verification.expires_at <= timezone.now()
        ):
            verification.status = TenantVerification.Status.EXPIRED
            verification.save(update_fields=["status", "updated_at"])
            user = verification.user
            if user.tenant_verified:
                user.tenant_verified = False
                user.save(update_fields=["tenant_verified"])


class TenantKycFileView(APIView):
    """Serve one tenant's verification document — the tenant or admin only.

    Same privacy contract as the landlord KYC file endpoint: never served from
    MEDIA_URL; non-owners get a 404 (not 403) so a guessed user id doesn't even
    confirm a verification exists.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Tenant KYC"],
        summary="Download a tenant verification document",
        description="Authenticated. Owner or admin only; otherwise 404.",
    )
    def get(self, request, user_id):
        verification = get_object_or_404(TenantVerification, user_id=user_id)
        if not (_is_admin(request.user) or verification.user_id == request.user.id):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not verification.file:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(verification.file.open("rb"))
        response["Content-Disposition"] = f'inline; filename="{verification.file.name}"'
        return response


class TenantKycPendingApplicationsView(APIView):
    """Admin review queue for tenant verifications."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Tenant KYC"],
        summary="List pending tenant verifications",
        description="Admin only. Tenants with a pending verification, oldest first, "
        "each with the admin-gated document URL.",
        responses=TenantKycPendingSerializer(many=True),
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        pending = (
            TenantVerification.objects.filter(status=TenantVerification.Status.PENDING)
            .select_related("user")
            .order_by("created_at")
        )
        return Response(
            TenantKycPendingSerializer(
                [v.user for v in pending], many=True, context={"request": request}
            ).data
        )


class TenantKycReviewView(APIView):
    """Admin decision on a tenant's verification: approve (flips
    ``tenant_verified`` on, sets expiry), reject, or request re-submission.
    Every decision is audited (``tenant_kyc.*``) and the tenant is notified;
    rejections also get a branded email with the reviewer's note.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Tenant KYC"],
        summary="Review a tenant verification",
        description="Admin only. `decision`: approved | rejected | needs_review.",
        request=TenantKycReviewRequestSerializer,
        responses=TenantKycPendingSerializer,
    )
    def post(self, request, user_id):
        if not _is_admin(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TenantKycReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target = get_object_or_404(User, pk=user_id)
        verification = get_object_or_404(TenantVerification, user=target)
        decision = serializer.validated_data["decision"]
        note = serializer.validated_data.get("note", "")

        if verification.status != TenantVerification.Status.PENDING:
            return Response(
                {"detail": "Only pending verifications can be reviewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from datetime import timedelta

        from django.db import transaction

        with transaction.atomic():
            if decision == "approved":
                verification.status = TenantVerification.Status.VERIFIED
                verification.expires_at = timezone.now() + timedelta(days=TENANT_KYC_EXPIRY_DAYS)
                target.tenant_verified = True
            elif decision == "needs_review":
                verification.status = TenantVerification.Status.NEEDS_REVIEW
                target.tenant_verified = False
            else:  # rejected
                verification.status = TenantVerification.Status.REJECTED
                target.tenant_verified = False
            verification.review_note = note
            verification.reviewed_at = timezone.now()
            verification.save()
            target.save(update_fields=["tenant_verified"])

            from audit.services import log_action

            log_action(
                actor=request.user,
                action=f"tenant_kyc.{decision}",
                target=target,
                request=request,
                detail={
                    "note": note,
                    "verification_id": verification.pk,
                    "expires_at": verification.expires_at.isoformat()
                    if verification.expires_at
                    else None,
                },
            )

            if decision == "approved":
                create_notification(
                    user=target,
                    notification_type=Notification.Type.TENANT_KYC_APPROVED,
                    title="Identity verified 🎉",
                    message=(
                        "Your identity was verified. Landlords can now see the "
                        "verified-tenant badge when you inquire or book."
                    ),
                    action_url="/dashboard",
                )
            else:
                create_notification(
                    user=target,
                    notification_type=(
                        Notification.Type.TENANT_KYC_REJECTED
                        if decision == "rejected"
                        else Notification.Type.TENANT_KYC_NEEDS_REVIEW
                    ),
                    title=(
                        "Identity verification not approved"
                        if decision == "rejected"
                        else "Identity verification needs your attention"
                    ),
                    message=(
                        note
                        or (
                            "Your identity document could not be verified. "
                            "Please re-upload a clear copy."
                        )
                    ),
                    action_url="/dashboard",
                )
                if decision == "rejected":
                    transaction.on_commit(
                        lambda: send_html_email(
                            subject="Your Rentora tenant verification needs attention",
                            to_email=target.email,
                            template_name="tenant_kyc_rejected",
                            context={
                                "user": target,
                                "note": note,
                                "action_url": f"{settings.FRONTEND_URL}/dashboard",
                            },
                        )
                    )
        return Response(TenantKycPendingSerializer(target, context={"request": request}).data)


class ReferralInfoView(APIView):
    """Referral program (Phase 10): the user's code, share link and stats.

    ``GET /api/v1/users/referral/`` returns the authenticated user's referral
    code, a ready-to-share signup link, and how many accounts they've brought
    in (with usernames/join dates). The frontend renders the invite card from
    this single payload.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Users"],
        summary="Referral code + stats",
        description="The authenticated user's referral code, share link, and invited users.",
    )
    def get(self, request):
        referrals = request.user.referrals.order_by("date_joined")
        invited = [
            {
                "username": u.username,
                "joined_at": u.date_joined.isoformat(),
            }
            for u in referrals
        ]
        return Response(
            {
                "code": request.user.referral_code,
                "link": (f"{settings.FRONTEND_URL}/auth/register?ref={request.user.referral_code}"),
                "invited_count": len(invited),
                "invited": invited,
            }
        )
