"""Shared helpers for chat real-time broadcasting.

Keeping the group-name convention and the broadcast call in one place means the
REST endpoint and the WebSocket consumer emit identical events to the same
channel group, so a message sent over HTTP still reaches connected sockets.
"""

from __future__ import annotations

import datetime
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def room_group_name(room_id: int | str) -> str:
    """Channel-layer group name for a chat room."""
    return f"chat_{room_id}"


def broadcast_message(room_id: int | str, message: dict[str, Any]) -> None:
    """Send a serialized message to every socket subscribed to the room.

    Safe to call from synchronous code (views, DRF) — wraps the async
    ``group_send`` via ``async_to_sync``. No-ops if no channel layer is
    configured.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        room_group_name(room_id),
        {"type": "chat_message", "message": message},
    )


def broadcast_read_receipt(room_id: int | str, user_id: int, last_read_at: datetime.datetime) -> None:
    """Notify sockets subscribed to the room that ``user_id`` has read up to
    ``last_read_at``. Used by the REST "fetch messages" path (the WebSocket
    consumer broadcasts its own read receipts directly)."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        room_group_name(room_id),
        {
            "type": "read_receipt",
            "user_id": user_id,
            "last_read_at": last_read_at.isoformat(),
            # No live socket originated this (it came from a REST call), so
            # there's nothing to exclude from the broadcast.
            "sender_channel": None,
        },
    )
