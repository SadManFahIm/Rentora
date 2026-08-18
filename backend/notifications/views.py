from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, PushSubscription
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

    @extend_schema(
        tags=["Notifications"],
        summary="Smart alert ranking (Tier 4)",
        description=(
            "The user's notifications ranked by an explainable priority score: "
            "safety/financial alerts first, booking next, recency + saved-search "
            "relevance as boosts. Each item carries `priority` (0-100) and a "
            "plain-language `reason` so the ranking is transparent."
        ),
        responses=inline_serializer(
            "SmartAlertsResponse",
            fields={"alerts": serializers.ListField(child=serializers.DictField())},
        ),
    )
    @action(detail=False, methods=["get"], url_path="smart")
    def smart_alerts(self, request: Request) -> Response:
        """Return the user's alerts sorted by priority (highest first)."""
        from .smart_alerts import rank_alerts

        qs = self.get_queryset()[:100]
        ranked = rank_alerts(qs)
        by_id = {n.id: NotificationSerializer(n).data for n in qs}
        alerts = [
            {**by_id[r["id"]], "priority": r["priority"], "reason": r["reason"]}
            for r in ranked
            if r["id"] in by_id
        ]
        return Response({"alerts": alerts})
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"count": count})


class PushSubscriptionView(APIView):
    """Register / unregister a browser Web Push subscription.

    The browser sends the subscription it built with the app's VAPID public
    key; we store it and start pushing notifications to it. POST is
    idempotent (same endpoint re-saved), DELETE removes it.

    Endpoints
    ---------
    * ``POST   /api/v1/notifications/push/subscribe/`` — ``{endpoint, auth, p256dh}``
    * ``DELETE /api/v1/notifications/push/subscribe/`` — ``{endpoint}``
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        summary="Register a push subscription",
        description="Store a browser Web Push subscription for the authenticated user.",
        request=inline_serializer(
            "PushSubscribeRequest",
            fields={
                "endpoint": serializers.URLField(),
                "auth": serializers.CharField(),
                "p256dh": serializers.CharField(),
            },
        ),
        responses=inline_serializer(
            "PushSubscribeResponse",
            fields={"status": serializers.CharField()},
        ),
    )
    def post(self, request: Request) -> Response:
        endpoint = request.data.get("endpoint", "").strip()
        auth = request.data.get("auth", "").strip()
        p256dh = request.data.get("p256dh", "").strip()
        if not endpoint or not auth or not p256dh:
            return Response(
                {"detail": "endpoint, auth and p256dh are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={"auth": auth, "p256dh": p256dh},
        )
        return Response(
            {"status": "created" if created else "updated"},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Notifications"],
        summary="Unregister a push subscription",
        description="Remove a stored push subscription by its endpoint.",
        request=inline_serializer(
            "PushUnsubscribeRequest",
            fields={"endpoint": serializers.URLField()},
        ),
        responses=inline_serializer(
            "PushUnsubscribeResponse",
            fields={"status": serializers.CharField()},
        ),
    )
    def delete(self, request: Request) -> Response:
        endpoint = request.data.get("endpoint", "").strip()
        if not endpoint:
            return Response(
                {"detail": "endpoint is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response({"status": "deleted" if deleted else "not_found"})
