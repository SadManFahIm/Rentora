"""Subscription lifecycle maintenance (Celery).

With no broker these run eagerly (see ``CELERY_TASK_ALWAYS_EAGER``); in
production ``celery beat`` runs them on schedule.
"""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from audit.services import log_action
from notifications.models import Notification
from notifications.utils import create_notification

from .models import Subscription


@shared_task
def process_subscription_renewals() -> int:
    """Expire subscriptions whose period has ended.

    An ACTIVE subscription whose ``current_period_end`` has passed becomes
    EXPIRED (unless the user renewed in the meantime — the renew flow
    extends the period, so it would no longer match this filter). Returns
    the number expired.
    """
    now = timezone.now()
    expired = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE, current_period_end__lte=now
    ).select_related("user", "plan")
    count = 0
    for sub in expired:
        sub.status = Subscription.Status.EXPIRED
        sub.save(update_fields=["status", "updated_at"])
        create_notification(
            user=sub.user,
            notification_type=Notification.Type.SUBSCRIPTION_EXPIRED,
            title="Subscription expired",
            message=f"Your {sub.plan.name} plan has expired. Renew to keep your features active.",
            action_url="/dashboard?tab=monetization",
        )
        log_action(actor=None, action="subscription.expired", target=sub)
        count += 1
    return count


@shared_task
def send_subscription_reminders() -> int:
    """Remind users 3 days before their subscription period ends."""
    now = timezone.now()
    horizon = now + timedelta(days=3)
    subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__lte=horizon,
        current_period_end__gte=now,
        cancel_at_period_end=False,
    ).select_related("user", "plan")
    from notifications.emails import send_html_email

    for sub in subs:
        create_notification(
            user=sub.user,
            notification_type=Notification.Type.SUBSCRIPTION_RENEWAL_REMINDER,
            title="Subscription renewing soon",
            message=f"Your {sub.plan.name} plan renews on {sub.current_period_end:%d %b %Y}. "
            "Manage it from your dashboard.",
            action_url="/dashboard?tab=monetization",
        )
        if sub.user.email:
            send_html_email(
                subject="Your Rentora subscription renews soon",
                to_email=sub.user.email,
                template_name="subscription_reminder",
                context={
                    "user": sub.user,
                    "plan_name": sub.plan.name,
                    "period_end": sub.current_period_end,
                },
            )
    return subs.count()
