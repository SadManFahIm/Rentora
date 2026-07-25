"""WebSocket consumer for real-time chat.

Auth is handled upstream by :class:`config.middleware.JWTAuthMiddleware`, which
places the authenticated user on ``scope["user"]`` (or ``AnonymousUser``).
"""

from __future__ import annotations

import json
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from config.sanitizers import sanitize_text

from .models import ChatRoom, ChatRoomMembership, Message
from .serializers import MessageSerializer
from .utils import room_group_name

# Application-defined WebSocket close codes.
WS_CLOSE_UNAUTHENTICATED = 4401
WS_CLOSE_FORBIDDEN = 4403


class ChatConsumer(AsyncWebsocketConsumer):
    """Handles a single client's connection to one chat room."""

    async def connect(self) -> None:
        self.user = self.scope.get("user")
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.group_name = room_group_name(self.room_id)

        if self.user is None or not self.user.is_authenticated:
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)
            return

        if not await self._is_member(self.room_id, self.user.pk):
            await self.close(code=WS_CLOSE_FORBIDDEN)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        # ``group_name`` is unset only if connect() failed before assigning it.
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data=None) -> None:
        """Parse an inbound frame, persist the message, broadcast it."""
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON payload.")
            return

        content = sanitize_text(data.get("content", "")) or ""
        if not content.strip():
            await self._send_error("Message content cannot be empty.")
            return

        message_type = data.get("message_type", Message.MessageType.TEXT)
        file_url = data.get("file_url", "")

        payload = await self._save_message(content, message_type, file_url)

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat_message", "message": payload},
        )

    async def chat_message(self, event: dict[str, Any]) -> None:
        """Group handler → forward a broadcast message to this client."""
        await self.send(
            text_data=json.dumps({"type": "chat_message", "message": event["message"]})
        )

    # ---- helpers ----

    async def _send_error(self, detail: str) -> None:
        await self.send(text_data=json.dumps({"type": "error", "detail": detail}))

    @database_sync_to_async
    def _is_member(self, room_id: int | str, user_id: int) -> bool:
        return ChatRoomMembership.objects.filter(
            chat_room_id=room_id, user_id=user_id
        ).exists()

    @database_sync_to_async
    def _save_message(self, content: str, message_type: str, file_url: str) -> dict:
        """Persist the message, bump the room, and return the serialized dict."""
        valid_types = {c[0] for c in Message.MessageType.choices}
        if message_type not in valid_types:
            message_type = Message.MessageType.TEXT

        message = Message.objects.create(
            chat_room_id=self.room_id,
            sender=self.user,
            content=content,
            message_type=message_type,
            file_url=file_url,
        )
        # Bump the room so it sorts to the top of the caller's room list.
        ChatRoom.objects.filter(pk=self.room_id).update(updated_at=timezone.now())
        return MessageSerializer(message).data
