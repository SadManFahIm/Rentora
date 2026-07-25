"""WebSocket consumer for real-time chat.

Auth is handled upstream by :class:`config.middleware.JWTAuthMiddleware`, which
places the authenticated user on ``scope["user"]`` (or ``AnonymousUser``).

Inbound frames are dispatched by their ``type``:

- ``"message"`` (or omitted, for backward compatibility) — persist + broadcast
  a chat message.
- ``"typing"`` — ephemeral typing-indicator broadcast, never persisted.
- ``"mark_read"`` — bump the caller's ``last_read_at`` and broadcast a read
  receipt.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from config.sanitizers import sanitize_text

from . import presence
from .models import ChatRoom, ChatRoomMembership, Message
from .serializers import MessageSerializer
from .utils import room_group_name

# Application-defined WebSocket close codes.
WS_CLOSE_UNAUTHENTICATED = 4401
WS_CLOSE_FORBIDDEN = 4403

# How long a disconnected user is still considered online, to ride out a
# quick reconnect (page refresh, brief network blip) without flickering
# their status to "offline" and back.
OFFLINE_GRACE_SECONDS = 5


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

        await sync_to_async(presence.mark_online)(self.user.pk)
        # Opening the room counts as reading it.
        await self._mark_read_and_broadcast()

    async def disconnect(self, code: int) -> None:
        # ``group_name`` is unset only if connect() failed before assigning it.
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

        if getattr(self, "user", None) is not None and self.user.is_authenticated:
            # Fire-and-forget: don't block the disconnect handler on the delay.
            asyncio.create_task(self._delayed_mark_offline(self.user.pk))

    async def receive(self, text_data: str | None = None, bytes_data=None) -> None:
        """Parse an inbound frame and dispatch it by ``type``."""
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON payload.")
            return

        event_type = data.get("type", "message")
        handler = {
            "message": self._handle_message,
            "typing": self._handle_typing,
            "mark_read": self._handle_mark_read,
        }.get(event_type)

        if handler is None:
            await self._send_error(f"Unknown event type '{event_type}'.")
            return

        await handler(data)

    # ---- inbound event handlers ----

    async def _handle_message(self, data: dict[str, Any]) -> None:
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

    async def _handle_typing(self, data: dict[str, Any]) -> None:
        """Ephemeral typing indicator — never persisted. The client is
        responsible for clearing it locally after ~5s of silence; the server
        just relays whatever state it's told."""
        is_typing = bool(data.get("is_typing", False))
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "typing_indicator",
                "user_id": self.user.pk,
                "user_name": self.user.get_full_name() or self.user.username,
                "is_typing": is_typing,
                "sender_channel": self.channel_name,
            },
        )

    async def _handle_mark_read(self, data: dict[str, Any]) -> None:
        await self._mark_read_and_broadcast()

    # ---- group event handlers (channel layer -> client) ----

    async def chat_message(self, event: dict[str, Any]) -> None:
        """Group handler → forward a broadcast message to this client."""
        await self.send(
            text_data=json.dumps({"type": "chat_message", "message": event["message"]})
        )

    async def typing_indicator(self, event: dict[str, Any]) -> None:
        if event.get("sender_channel") == self.channel_name:
            return  # Don't echo the typing state back to whoever sent it.
        await self.send(
            text_data=json.dumps(
                {
                    "type": "typing_indicator",
                    "user_id": event["user_id"],
                    "user_name": event["user_name"],
                    "is_typing": event["is_typing"],
                }
            )
        )

    async def read_receipt(self, event: dict[str, Any]) -> None:
        if event.get("sender_channel") == self.channel_name:
            return  # Don't echo the reader's own receipt back to them.
        await self.send(
            text_data=json.dumps(
                {
                    "type": "read_receipt",
                    "user_id": event["user_id"],
                    "last_read_at": event["last_read_at"],
                }
            )
        )

    # ---- helpers ----

    async def _send_error(self, detail: str) -> None:
        await self.send(text_data=json.dumps({"type": "error", "detail": detail}))

    async def _mark_read_and_broadcast(self) -> None:
        last_read_at = await self._mark_read()
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "read_receipt",
                "user_id": self.user.pk,
                "last_read_at": last_read_at.isoformat(),
                "sender_channel": self.channel_name,
            },
        )

    async def _delayed_mark_offline(self, user_id: int) -> None:
        await asyncio.sleep(OFFLINE_GRACE_SECONDS)
        await sync_to_async(presence.mark_offline)(user_id)

    @database_sync_to_async
    def _is_member(self, room_id: int | str, user_id: int) -> bool:
        return ChatRoomMembership.objects.filter(
            chat_room_id=room_id, user_id=user_id
        ).exists()

    @database_sync_to_async
    def _mark_read(self):
        now = timezone.now()
        ChatRoomMembership.objects.filter(
            chat_room_id=self.room_id, user_id=self.user.pk
        ).update(last_read_at=now)
        return now

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
