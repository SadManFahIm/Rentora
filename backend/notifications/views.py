from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


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
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request: Request) -> Response:
        """Mark all of the user's unread notifications as read.

        Returns ``{"marked_count": N}`` where ``N`` is the number of rows that
        were actually flipped (0 when nothing was unread).
        """
        marked_count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"marked_count": marked_count})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        """Return ``{"count": N}`` — the user's unread notification count."""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"count": count})
