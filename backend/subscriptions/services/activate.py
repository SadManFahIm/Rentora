"""Side effects that fire when a subscription payment turns SUCCESS.

Called from ``payments.views._apply_success_side_effects`` (inside the same
``transaction.atomic()`` that commits the SUCCESS transition) so the
subscription activation commits atomically with the payment.

Handles both the initial activation (a PENDING subscription) and a renewal
(an ACTIVE subscription whose payment is the new checkout — the period is
extended from the current period end).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from audit.services import log_action
from notifications.models import Notification
from notifications.utils import create_notification
from subscriptions.models import Subscription


def _period_delta(subscription: Subscription) -> timedelta:
    days = getattr(settings, "SUBSCRIPTION_PERIOD_DAYS", {"monthly": 30, "yearly": 365}).get(
        subscription.plan.billing_cycle
    )
    return timedelta(days=days or 30)


def activate_on_payment(payment) -> None:
    """Activate/extend the subscription attached to a successful payment.

    No-op when the payment isn't attached to a subscription (booking /
    listing-promotion payments), so callers never need to branch.
    """
    sub = Subscription.objects.select_for_update().filter(payment=payment).first()
    if sub is None:
        return

    now = timezone.now()
    renewed = sub.status == Subscription.Status.ACTIVE and sub.current_period_end
    if (
        sub.status == Subscription.Status.ACTIVE
        and sub.current_period_end
        and sub.current_period_end > now
    ):
        sub.current_period_end = sub.current_period_end + _period_delta(sub)
    else:
        sub.current_period_start = now
        sub.current_period_end = now + _period_delta(sub)
        sub.status = Subscription.Status.ACTIVE
    sub.cancel_at_period_end = False
    sub.save(update_fields=["status", "current_period_start", "current_period_end", "updated_at"])

    headline = "Subscription renewed" if renewed else "Subscription active"
    create_notification(
        user=sub.user,
        notification_type=Notification.Type.SUBSCRIPTION_ACTIVE,
        title=headline,
        message=f"Your {sub.plan.name} plan is active until "
        f"{sub.current_period_end:%d %b %Y}. Enjoy your features.",
        action_url="/dashboard?tab=monetization",
    )
    log_action(
        actor=sub.user,
        action="subscription.activated" if not renewed else "subscription.renewed",
        target=sub,
        detail={"plan": sub.plan.code, "payment_id": payment.pk},
    )

    from monetization.services.ledger import record_entry

    record_entry(
        entry_type="subscription_renewal" if renewed else "subscription_payment",
        scope="subscription",
        user=sub.user,
        gross=payment.amount,
        platform_amount=payment.amount,
        partner_amount=0,
        source=payment,
        idempotency_key=f"subscription-payment-{payment.transaction_id}",
        detail={"plan": sub.plan.code, "subscription_id": sub.pk},
    )
