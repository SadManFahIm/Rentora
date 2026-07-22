from __future__ import annotations

from django.contrib.auth import get_user_model

from config.sanitizers import sanitize_text

from .models import Notification

User = get_user_model()


def create_notification(
    user: "User",
    notification_type: str,
    title: str,
    message: str,
    action_url: str = "",
) -> Notification:
    """Create and persist a :class:`~notifications.models.Notification`.

    This is the single entry point for emitting notifications so callers
    (views, signals, management commands) never touch the model directly.

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
    return Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=sanitize_text(title),
        message=sanitize_text(message),
        action_url=action_url,
    )
