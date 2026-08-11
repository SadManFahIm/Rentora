"""Celery tasks for the users app — KYC review-SLA breach alerts."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def alert_kyc_sla_breaches():
    """Check the KYC review queue and alert admins when an SLA is breached.

    Runs daily via Celery beat. A breach is one of:

    - ``oldest_pending`` — the oldest pending application has been waiting
      longer than ``SLA_OLDEST_PENDING_BREACH_H`` (48h).
    - ``trend_negative`` — decisions this week trail last week's count, so
      the queue is growing faster than it's being cleared.

    Every admin gets one in-app notification + one email per breached
    condition, deduplicated per day (a second run on the same day is a no-op)
    so a retried cron never spams the team.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from django.utils import timezone

    from config.sanitizers import sanitize_text
    from notifications.email_guard import send_alert_email
    from notifications.models import EmailDeliveryLog, Notification
    from notifications.utils import broadcast_notification

    from .models import KycDocument
    from .views import SLA_OLDEST_PENDING_BREACH_H

    User = get_user_model()
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    resolved = KycDocument.objects.exclude(reviewed_at=None)
    last_7d_decisions = resolved.filter(reviewed_at__gte=week_ago).count()
    prev_7d_decisions = resolved.filter(
        reviewed_at__gte=two_weeks_ago, reviewed_at__lt=week_ago
    ).count()

    oldest_pending = (
        KycDocument.objects.filter(status=KycDocument.Status.PENDING).order_by("created_at").first()
    )
    pending_oldest_hours = (
        round((now - oldest_pending.created_at).total_seconds() / 3600, 1)
        if oldest_pending
        else None
    )

    breaches = []
    if pending_oldest_hours is not None and pending_oldest_hours > SLA_OLDEST_PENDING_BREACH_H:
        breaches.append(
            {
                "key": "oldest_pending",
                "title": "KYC queue breach — application stuck",
                "message": (
                    f"The oldest pending KYC application has been waiting "
                    f"{pending_oldest_hours:.0f}h (limit {SLA_OLDEST_PENDING_BREACH_H:.0f}h). "
                    f"Review the queue to keep verification promises."
                ),
            }
        )
    if last_7d_decisions < prev_7d_decisions:
        breaches.append(
            {
                "key": "trend_negative",
                "title": "KYC decisions slipping this week",
                "message": (
                    f"{prev_7d_decisions} decisions last week vs "
                    f"{last_7d_decisions} this week — the review queue is "
                    f"growing. Consider extra review capacity."
                ),
            }
        )

    if not breaches:
        return {"breaches": [], "alerted": False}

    admins = User.objects.filter(Q(is_staff=True) | Q(role=User.Role.ADMIN)).distinct()

    today = timezone.localdate()
    alerted = 0
    emails_sent = 0
    emails_skipped = 0
    emails_failed = 0
    for breach in breaches:
        title = breach["title"]
        message = breach["message"]
        for admin in admins:
            # get_or_create is the atomic dedupe: the title carries the date,
            # so (admin, type, title) is unique per day per condition. A
            # retried or racing beat run cannot stack identical alerts even
            # if it runs concurrently.
            notification, created = Notification.objects.get_or_create(
                user=admin,
                notification_type=Notification.Type.KYC_SLA_BREACH,
                title=sanitize_text(f"{title} — {today:%b %d}"),
                defaults={
                    "message": sanitize_text(message),
                    "action_url": "/dashboard?tab=kyc",
                },
            )
            if not created:
                continue
            # Live WebSocket push — the admin's open dashboard/Navbar socket
            # receives this instantly via the notifications channel layer.
            broadcast_notification(notification)
            # Emails are best-effort and throttled (daily budget + failure
            # backoff) so a misbehaving SMTP can never spam the team.
            delivery = send_alert_email(
                subject=f"[{settings.SITE_NAME}] {title}",
                to_email=admin.email,
                template_name="kyc_sla_alert",
                context={
                    "user": admin,
                    "title": title,
                    "message": message,
                    "action_url": f"{settings.FRONTEND_URL}/dashboard?tab=kyc",
                },
            )
            if delivery.status == EmailDeliveryLog.Status.SENT:
                emails_sent += 1
            elif delivery.status == EmailDeliveryLog.Status.SKIPPED:
                emails_skipped += 1
            else:
                emails_failed += 1
            alerted += 1

    logger.info(
        "KYC SLA breach alert: %s condition(s), %d admin notification(s), "
        "%d email(s) sent, %d skipped, %d failed",
        len(breaches),
        alerted,
        emails_sent,
        emails_skipped,
        emails_failed,
    )
    return {
        "breaches": [b["key"] for b in breaches],
        "alerted": alerted,
        "websocket_pushed": alerted,
        "emails_sent": emails_sent,
        "emails_skipped": emails_skipped,
        "emails_failed": emails_failed,
    }
