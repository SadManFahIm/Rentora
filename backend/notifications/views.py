from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


@extend_schema_view(
    list=extend_schema(
        tags=["Notifications"],
        summary="List notifications",
        description="The authenticated user's notifications, paginated, newest first.",
    ),
    retrieve=extend_schema(tags=["Notifications"], summary="Retrieve a notification"),
    partial_update=extend_schema(
        tags=["Notifications"],
        summary="Mark a notification read/unread",
        description="Patch `is_read` on a single notification.",
    ),
    update=extend_schema(tags=["Notifications"], summary="Update a notification (is_read)"),
)
class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Read and manage the authenticated user's notifications.

    Endpoints
    ---------
    * ``GET   /api/v1/notifications/``                 — paginated list (own only).
    * ``GET   /api/v1/notifications/{id}/``            — retrieve one.
    * ``PATCH /api/v1/notifications/{id}/``            — mark single read/unread.
    * ``POST  /api/v1/notifications/mark-all-read/``   — mark every unread read.
    * ``GET   /api/v1/notifications/unread-count/``    — number of unread items.
    """

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    # No PUT (full replace) or DELETE: notifications are server-authored and
    # the only client mutation is toggling ``is_read`` via PATCH.
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        """Restrict every action to the requesting user's notifications."""
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    @extend_schema(
        tags=["Notifications"],
        summary="Mark all notifications read",
        description="Flip every unread notification to read. Returns the number changed.",
        request=None,
        responses=inline_serializer(
            "MarkAllReadResponse",
            fields={"marked_count": serializers.IntegerField()},
        ),
    )
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request: Request) -> Response:
        """Mark all of the user's unread notifications as read.

        Returns ``{"marked_count": N}`` where ``N`` is the number of rows that
        were actually flipped (0 when nothing was unread).
        """
        marked_count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"marked_count": marked_count})

    @extend_schema(
        tags=["Notifications"],
        summary="Unread notification count",
        description="Number of unread notifications for the authenticated user.",
        responses=inline_serializer(
            "UnreadCountResponse",
            fields={"count": serializers.IntegerField()},
        ),
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        """Return ``{"count": N}`` — the user's unread notification count."""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"count": count})
