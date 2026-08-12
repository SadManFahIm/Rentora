from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

from config.sanitizers import sanitize_text

from .models import Notification

User = get_user_model()


def notification_group_name(user_id: int) -> str:
    """Channel-layer group name for a user's notification socket(s)."""
    return f"notifications_{user_id}"


def create_notification(
    user: User,
    notification_type: str,
    title: str,
    message: str,
    action_url: str = "",
    meta: dict | None = None,
) -> Notification:
    """Create, persist, and push a :class:`~notifications.models.Notification`.

    This is the single entry point for emitting notifications so callers
    (views, signals, management commands) never touch the model directly —
    which also means every caller gets the real-time WebSocket push for free,
    with nothing further to wire up.

    Parameters
    ----------
    user:
        Recipient of the notification.
    notification_type:
        One of :class:`notifications.models.Notification.Type` values.
    title:
        Short headline (<= 200 chars).
    message:
        Full notification body.
    action_url:
        Optional client-side route the notification links to.

    Returns
    -------
    Notification
        The created, saved notification instance.

    Notes
    -----
    ``title`` and ``message`` are HTML-sanitized before persistence: they are
    frequently interpolated from user-controlled data (e.g. a room title), so
    stripping markup here neutralises stored XSS at the single write path.
    """
    notification = Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=sanitize_text(title),
        message=sanitize_text(message),
        action_url=action_url,
        meta=meta or {},
    )
    broadcast_notification(notification)
    # Best-effort browser push: the same notification lands on subscribed
    # devices even when the user isn't in the app. Never blocks or raises.
    from .webpush import send_push_to_user

    send_push_to_user(user, notification.title, notification.message, notification.action_url)
    return notification


def broadcast_notification(notification: Notification) -> None:
    """Push the notification to the recipient's live socket(s), if any.

    Safe to call from synchronous code (this whole module is sync) — wraps
    the async ``group_send`` via ``async_to_sync``, mirroring
    ``chat/utils.py``'s ``broadcast_message``. No-ops if no channel layer is
    configured, and if the user isn't connected the group simply has no
    members — either way this never raises, so a notification is never lost
    just because nobody was listening.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    # Imported lazily to avoid a serializers -> utils -> serializers cycle
    # (NotificationSerializer doesn't import this module, but keeping the
    # import local here makes that non-dependency explicit).
    from .serializers import NotificationSerializer

    data: dict[str, Any] = NotificationSerializer(notification).data
    async_to_sync(channel_layer.group_send)(
        notification_group_name(notification.user_id),
        {"type": "notification", "data": data},
    )
