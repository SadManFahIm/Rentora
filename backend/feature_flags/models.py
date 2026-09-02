"""Centralized feature flags (Phase 16).

Replaces scattering ``if True`` / hardcoded IDs through the codebase with a
runtime, DB-backed flag service supporting:

* enabled/disabled
* environment targeting
* user/role targeting
* percentage rollout (deterministic bucketing)

Flags are safe: unknown or disabled flags return ``False``, lookups are cached
for 30s, and every flag carries an owner, purpose and cleanup plan so dead
flags get removed instead of accumulating.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models

from config.cache_utils import safe_cache_delete, safe_cache_get, safe_cache_set


class FeatureFlag(models.Model):
    class Status(models.TextChoices):
        ENABLED = "enabled", "Enabled"
        DISABLED = "disabled", "Disabled"
        PARTIAL = "partial", "Partial rollout"

    key = models.CharField(max_length=128, unique=True)
    label = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    owner = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DISABLED)
    rollout_percentage = models.PositiveIntegerField(default=0)  # 0..100
    environments = models.JSONField(default=list, blank=True)  # empty = all
    roles = models.JSONField(default=list, blank=True)  # empty = all
    user_ids = models.JSONField(default=list, blank=True)  # explicit allow-list
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cleanup_plan = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    def applies_to_environment(self) -> bool:
        if not self.environments:
            return True
        env = getattr(settings, "ENV_NAME", "dev")
        return env in self.environments

    def applies_to_user(self, user) -> bool:
        if user is not None and user.is_authenticated:
            if self.roles and getattr(user, "role", None) not in self.roles:
                return False
            if self.user_ids and user.id not in self.user_ids:
                return False
        return True

    def in_rollout(self, ident: str) -> bool:
        # nosec B324: MD5 here is deterministic bucketing (stable rollout split),
        # not a security primitive — collisions only affect bucket spread.
        bucket = int(hashlib.md5(f"{self.key}:{ident}".encode()).hexdigest()[:8], 16) % 100  # nosec B324
        return bucket < self.rollout_percentage


FLAG_CACHE_TTL_SECONDS = 30


def _flag_cache_key(key: str) -> str:
    return f"feature_flag:{key}"


def get_flag(key: str) -> FeatureFlag | None:
    cached = safe_cache_get(_flag_cache_key(key))
    if cached is not None:
        return cached
    try:
        flag = FeatureFlag.objects.filter(key=key).first()
    except Exception:
        return None
    safe_cache_set(_flag_cache_key(key), flag, timeout=FLAG_CACHE_TTL_SECONDS)
    return flag


def _identifier(user, anonymous_id: str | None, request) -> str:
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.id}"
    if anonymous_id:
        return f"anon:{anonymous_id}"
    meta = getattr(request, "META", {}) if request is not None else {}
    return f"ip:{meta.get('REMOTE_ADDR', 'unknown')}"


def is_enabled(key: str, user=None, request=None, anonymous_id: str | None = None) -> bool:
    """Whether a flag is active for the current context. Never raises."""
    try:
        flag = get_flag(key)
        if flag is None or flag.status == FeatureFlag.Status.DISABLED:
            return False
        if flag.status == FeatureFlag.Status.ENABLED:
            return flag.applies_to_environment() and flag.applies_to_user(user)
        # Partial rollout: deterministic per-identifier bucketing.
        if not flag.applies_to_environment() or not flag.applies_to_user(user):
            return False
        return flag.in_rollout(_identifier(user, anonymous_id, request))
    except Exception:
        return False


def rollout_for(key: str, user=None, request=None, anonymous_id: str | None = None) -> int:
    """0-100 deterministic bucket for diagnostics (testing/rollout dashboards)."""
    flag = get_flag(key)
    if flag is None:
        return 0
    return flag.rollout_percentage


VOICE_RENTAL_AGENT = "ai.voice_rental_agent"

FEATURE_IDS: list[str] = [VOICE_RENTAL_AGENT]


def invalidate_cache(key: str | None = None) -> None:
    """Drop the cached flag(s). All flags when ``key`` is None."""
    try:
        if key:
            safe_cache_delete(_flag_cache_key(key))
        else:
            for flag_key in FeatureFlag.objects.values_list("key", flat=True):
                safe_cache_delete(_flag_cache_key(flag_key))
    except Exception:
        pass
