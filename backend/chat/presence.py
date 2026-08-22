"""Online-presence tracking backed by Django's cache framework.

Each live WebSocket connection registers a *lease*: a per-connection entry
(``connection_id`` -> last-seen timestamp) stored in one cache key per user.
A periodic heartbeat refreshes the timestamp; leases whose timestamp is stale
are pruned lazily on read (or fall off when the whole key expires), so a
worker that dies without firing ``disconnect`` (deploy kill, OOM, crash) can
never leave a user permanently stuck "online" — the previous reference-count
model leaked exactly that way because its keys had no expiry.

The public API is unchanged: ``mark_online`` / ``mark_offline`` /
``is_online`` / ``bulk_online_status``.

Uses whatever ``CACHES["default"]`` resolves to (LocMemCache in a single dev
process, Redis in production/multi-process — see ``config/settings``), so this
is correct regardless of how many worker processes serve sockets.
"""

from __future__ import annotations

import time

from django.conf import settings

from config.cache_utils import (
    safe_cache_delete,
    safe_cache_get,
    safe_cache_get_many,
    safe_cache_set,
)

_KEY_PREFIX = "chat:online:"


def _connection_ttl() -> int:
    """How long a lease lives without a heartbeat before it counts as gone.

    Read at call time so ``override_settings`` (tests) and late config take
    effect. Consumers heartbeat every ``PRESENCE_HEARTBEAT_INTERVAL`` seconds,
    so the TTL tolerates a couple of missed beats (scheduler hiccups, GC
    pauses) while still self-healing within a minute or two of a hard kill.
    """
    return int(getattr(settings, "PRESENCE_CONNECTION_TTL", 180))


def _key_ttl() -> int:
    """TTL for the whole user key: once every lease goes stale there is no
    reason to keep paying to store a dead key. > lease TTL so healthy
    connections never expire the key out from under a live user."""
    return _connection_ttl() * 2


# Back-compat alias: code that tracks a single socket per user without a
# connection id (older callers) uses this bucket.
_DEFAULT_CONNECTION = "default"


def _key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{user_id}"


def _now() -> float:
    return time.monotonic()


def _prune(leases: dict[str, float]) -> dict[str, float]:
    """Drop leases whose last heartbeat is older than the TTL."""
    cutoff = _now() - _connection_ttl()
    return {cid: ts for cid, ts in leases.items() if ts > cutoff}


def _write(user_id: int, leases: dict[str, float]) -> None:
    if leases:
        safe_cache_set(_key(user_id), leases, timeout=_key_ttl())
    else:
        safe_cache_delete(_key(user_id))


def _read(user_id: int) -> dict[str, float]:
    """Load a user's leases, pruning stale ones and persisting the cleanup.

    Presence is cache-optional (see config/cache_utils policy): a Redis outage
    degrades to "nobody online" rather than crashing the chat/socket flows.
    """
    leases = safe_cache_get(_key(user_id))
    if not isinstance(leases, dict):
        return {}
    pruned = _prune(leases)
    if len(pruned) != len(leases):
        _write(user_id, pruned)
    return pruned


def mark_online(user_id: int, connection_id: str | None = None) -> None:
    """Register a live connection for ``user_id`` (idempotent per connection)."""
    connection_id = connection_id or _DEFAULT_CONNECTION
    leases = _read(user_id)
    leases[connection_id] = _now()
    _write(user_id, leases)


def touch(user_id: int, connection_id: str | None = None) -> None:
    """Refresh a connection's lease (heartbeat). No-op if it's already gone."""
    connection_id = connection_id or _DEFAULT_CONNECTION
    leases = _read(user_id)
    if connection_id in leases:
        leases[connection_id] = _now()
        _write(user_id, leases)


def mark_offline(user_id: int, connection_id: str | None = None) -> None:
    """Remove one connection's lease, deleting the key when none remain."""
    connection_id = connection_id or _DEFAULT_CONNECTION
    leases = _read(user_id)
    if connection_id in leases:
        leases.pop(connection_id)
        _write(user_id, leases)


def is_online(user_id: int) -> bool:
    return bool(_read(user_id))


def bulk_online_status(user_ids: list[int]) -> dict[str, list[int]]:
    """Split ``user_ids`` into online/offline lists with a single cache round-trip.

    Read-only: does not prune, to avoid write amplification on a hot endpoint.
    A user is online if any lease is fresher than the TTL.
    """
    keys_by_id = {uid: _key(uid) for uid in user_ids}
    cached = safe_cache_get_many(list(keys_by_id.values()))
    cutoff = _now() - _connection_ttl()

    online: list[int] = []
    offline: list[int] = []
    for uid, key in keys_by_id.items():
        leases = cached.get(key)
        fresh = isinstance(leases, dict) and any(ts > cutoff for ts in leases.values())
        (online if fresh else offline).append(uid)
    return {"online": online, "offline": offline}
