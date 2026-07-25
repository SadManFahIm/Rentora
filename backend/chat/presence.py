"""Online-presence tracking backed by Django's cache framework.

A user may have more than one live connection (multiple tabs/devices), so
presence is a reference count, not a boolean: ``connect`` increments,
``disconnect`` decrements, and the user is "online" while the count is > 0.

Uses whatever ``CACHES["default"]`` resolves to (LocMemCache in a single dev
process, Redis in production/multi-process — see ``config/settings``), so
this is correct regardless of how many worker processes are serving sockets.
"""

from __future__ import annotations

from django.core.cache import cache

_KEY_PREFIX = "chat:online:"
# No expiry: connection count is maintained explicitly on connect/disconnect.
# (A TTL would be wrong here — it would silently mark a long-lived, otherwise
# idle connection as offline.)
_NO_EXPIRY = None


def _key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{user_id}"


def mark_online(user_id: int) -> None:
    """Increment the active-connection count for ``user_id``."""
    key = _key(user_id)
    try:
        cache.incr(key)
    except ValueError:
        # Key doesn't exist yet (first connection, or it previously expired).
        cache.set(key, 1, timeout=_NO_EXPIRY)


def mark_offline(user_id: int) -> None:
    """Decrement the active-connection count, removing the key at zero."""
    key = _key(user_id)
    try:
        remaining = cache.decr(key)
    except ValueError:
        return  # Already absent — nothing to do.
    if remaining <= 0:
        cache.delete(key)


def is_online(user_id: int) -> bool:
    return (cache.get(_key(user_id)) or 0) > 0


def bulk_online_status(user_ids: list[int]) -> dict[str, list[int]]:
    """Split ``user_ids`` into online/offline lists with a single cache round-trip."""
    keys_by_id = {uid: _key(uid) for uid in user_ids}
    cached = cache.get_many(list(keys_by_id.values()))

    online: list[int] = []
    offline: list[int] = []
    for uid, key in keys_by_id.items():
        (online if (cached.get(key) or 0) > 0 else offline).append(uid)
    return {"online": online, "offline": offline}
