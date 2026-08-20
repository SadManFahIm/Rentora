"""Server-side entitlement checks.

Every paid feature key is verified here — the client only renders UI based
on this server response. A user with an active plan that carries the feature
is entitled; otherwise a ``settings.SUBSCRIPTION_FREE_FEATURES`` whitelist
provides the free baseline. When subscriptions are disabled globally every
feature is open (safe local-development default).
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from subscriptions.models import Subscription


def active_subscription(user):
    """The user's live subscription, or None."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    now = timezone.now()
    return (
        Subscription.objects.filter(
            user=user,
            status=Subscription.Status.ACTIVE,
            current_period_end__gt=now,
        )
        .select_related("plan")
        .first()
    )


def check_entitlement(user, feature: str) -> bool:
    """True when ``user`` may use ``feature`` (server-side authority)."""
    if not getattr(settings, "SUBSCRIPTIONS_ENABLED", True):
        return True
    if feature in getattr(settings, "SUBSCRIPTION_FREE_FEATURES", []):
        return True
    sub = active_subscription(user)
    return sub is not None and sub.plan.has_feature(feature)


def current_plan_code(user) -> str | None:
    sub = active_subscription(user)
    return sub.plan.code if sub is not None else None
