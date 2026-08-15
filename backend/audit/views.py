from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLogEntry


class AuditLogEntrySerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default="")

    class Meta:
        model = AuditLogEntry
        fields = [
            "id",
            "actor",
            "actor_username",
            "action",
            "target_type",
            "target_id",
            "detail",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields


@extend_schema(
    tags=["Audit"],
    summary="Audit trail (admin)",
    description=(
        "Admin only. Append-only audit entries, newest first, at most 200. "
        "Optional `?prefix=moderation` filters by action prefix (e.g. "
        "`report`, `moderation`, `dispute`, `kyc`)."
    ),
    responses=AuditLogEntrySerializer(many=True),
)
class AuditTrailView(APIView):
    """Read-only admin view over the immutable audit log."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if not (user.is_staff or user.role == "admin"):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        qs = AuditLogEntry.objects.select_related("actor")
        prefix = request.query_params.get("prefix", "")
        if prefix:
            qs = qs.filter(action__startswith=f"{prefix}.")
        return Response(AuditLogEntrySerializer(qs[:200], many=True).data)
