"""Redis-cache hardening helpers (Phase 16).

Cache is a critical-but-optional dependency: a Redis outage must not take down
core product flows. These wrappers convert connection/malformed-response
failures into safe defaults so callers degrade gracefully instead of 500ing.

Policy (documented in docs/phase-16-hardening.md):

* cache-optional features (presence, semantic ranking, recommendations, map
  intel, pricing suggestions)  -> return None/False and continue;
* security-sensitive rate limiting keeps DRF's fail-closed behaviour (a Redis
  outage returns 500 rather than silently lifting the throttle);
* auth challenges (passkeys/OTP) fail closed: a missing cache raises so the
  operation cannot proceed without its integrity guarantee.
"""

from __future__ import annotations

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# (redis.exceptions.Error, ConnectionError) covers Redis down/hung + the
# Django cache backend's own wrapped errors.
_SAFE_EXCEPTIONS = (Exception,)  # broad catch: degrade, never crash the request


def safe_cache_get(key: str, default=None):
    """cache.get() that returns ``default`` on any cache failure."""
    try:
        return cache.get(key, default)
    except _SAFE_EXCEPTIONS:
        logger.warning("cache.get failed for %r; using default", key)
        return default


def safe_cache_set(key: str, value, timeout=None) -> bool:
    """cache.set() that returns False on failure instead of raising."""
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except _SAFE_EXCEPTIONS:
        logger.warning("cache.set failed for %r", key)
        return False


def safe_cache_add(key: str, value, timeout=None) -> bool:
    """cache.add() (atomic set-if-absent) that returns False on failure.

    Used for distributed locks / single-flight guards: a Redis failure is
    treated as "lock unavailable" so callers take the conservative path.
    """
    try:
        return bool(cache.add(key, value, timeout=timeout))
    except _SAFE_EXCEPTIONS:
        logger.warning("cache.add failed for %r", key)
        return False


def safe_cache_delete(key: str) -> bool:
    try:
        cache.delete(key)
        return True
    except _SAFE_EXCEPTIONS:
        logger.warning("cache.delete failed for %r", key)
        return False


def safe_cache_get_many(keys: list[str], default=None):
    """cache.get_many() that returns ``default`` on any cache failure."""
    try:
        return cache.get_many(keys)
    except _SAFE_EXCEPTIONS:
        logger.warning("cache.get_many failed for %d keys", len(keys))
        return default if default is not None else {}


def safe_cache_incr(
    key: str, delta: int = 1, default: int = 0, timeout: int | None = None
) -> int | None:
    """Increment a counter, seeding it first when absent. None on failure."""
    try:
        if cache.get(key) is None:
            cache.add(key, default, timeout=timeout)
        return cache.incr(key, delta)
    except _SAFE_EXCEPTIONS:
        logger.warning("cache.incr failed for %r", key)
        return None


def lock(key: str, timeout: int = 60) -> bool:
    """Non-blocking distributed lock via cache.add. Returns True if acquired.

    The lock auto-expires after ``timeout`` seconds so a crashed holder can
    never deadlock the rest of the system (stale locks self-heal).
    """
    return safe_cache_add(f"lock:{key}", "1", timeout=timeout)


def unlock(key: str) -> None:
    safe_cache_delete(f"lock:{key}")
