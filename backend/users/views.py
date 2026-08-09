from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.utils import create_notification

from .models import KycDocument, User
from .serializers import (
    KycAuditEntrySerializer,
    KycDocumentSerializer,
    KycPendingUserSerializer,
    KycReviewRequestSerializer,
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
        return Response(KycPendingUserSerializer(target, context={"request": request}).data)
