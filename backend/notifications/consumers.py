"""WebSocket consumer for real-time notification push.

Auth is handled upstream by :class:`config.middleware.JWTAuthMiddleware`, which
places the authenticated user on ``scope["user"]`` (or ``AnonymousUser``).

Server-push only — the client never sends anything meaningful over this
socket, it just listens. Each connected user is subscribed to their own group
so :func:`notifications.utils.create_notification` can push to them from
anywhere (a view, a signal handler, a management command) without knowing or
caring whether they're currently connected.
"""

from __future__ import annotations

import json
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .utils import notification_group_name

# Application-defined WebSocket close code.
WS_CLOSE_UNAUTHENTICATED = 4401


class NotificationConsumer(AsyncWebsocketConsumer):
    """One socket per connected user, subscribed to ``notifications_{user_id}``."""

    async def connect(self) -> None:
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)
            return

        self.group_name = notification_group_name(self.user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        # ``group_name`` is unset only if connect() closed before assigning it.
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data=None) -> None:
        """Server-push socket, but still answers heartbeat pings.

        The browser WebSocket API never surfaces protocol pings to JS (the
        runtime answers them silently), so the shared ``useWebSocket`` hook
        sends ``{"type": "ping"}`` and relies on the ``{"type": "pong"}`` reply
        to detect a half-open connection. Anything else is ignored — this
        socket has no meaningful inbound payloads.
        """
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get("type") == "ping":
            await self.send(
                text_data=json.dumps({"type": "pong", "server_time": timezone.now().isoformat()})
            )

    async def notification(self, event: dict[str, Any]) -> None:
        """Group handler → forward a pushed notification to this client."""
        await self.send(text_data=json.dumps({"type": "notification", "data": event["data"]}))
