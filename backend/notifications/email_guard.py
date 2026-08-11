"""Rate-limited delivery of alert emails (SLA breaches, fraud blasts, …).

``send_html_email`` is the raw, no-guard sender used for transactional mail
(OTP codes, booking updates) where every message matters. Scheduled alert
blasts are different: a misconfigured SMTP or a busy day must never turn into
an email storm against the same recipients. :func:`send_alert_email` wraps the
raw sender with two cheap, database-backed guards and records every decision
in :class:`~notifications.models.EmailDeliveryLog`:

- **Daily budget** — at most ``ALERT_EMAIL_DAILY_BUDGET`` *sent* messages per
  recipient per template per day. Only successful sends count towards the
  budget; throttled and failed attempts do not.
- **Failure backoff** — after a failed send, the recipient is not retried
  until ``ALERT_EMAIL_BACKOFF_HOURS * 2 ** (consecutive_failures - 1)`` have
  passed (exponential: 24h, 48h, 96h…, capped at 7 days). Consecutive
  failures are counted since the last successful send.

The ledger is the source of truth for both guards, so the behaviour is
consistent across processes (Celery workers, beat) with no extra
infrastructure, and the team can audit exactly what was sent, throttled, or
failed.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from .emails import send_html_email
from .models import EmailDeliveryLog

logger = logging.getLogger(__name__)

# Hard cap so a long outage can never grow the window indefinitely.
MAX_BACKOFF_HOURS = 7 * 24


def send_alert_email(
    *,
    subject: str,
    to_email: str,
    template_name: str,
    context: dict[str, Any] | None = None,
    daily_budget: int | None = None,
    backoff_hours: int | None = None,
) -> EmailDeliveryLog:
    """Send one rate-limited alert email and return its delivery-log entry.

    Never raises: email is best-effort and the guards must not take down the
    caller (a Celery beat task). Every path — sent, throttled, failed —
    persists an :class:`~notifications.models.EmailDeliveryLog` row and is
    logged.
    """
    budget = (
        daily_budget
        if daily_budget is not None
        else getattr(settings, "ALERT_EMAIL_DAILY_BUDGET", 3)
    )
    base_backoff = (
        backoff_hours
        if backoff_hours is not None
        else getattr(settings, "ALERT_EMAIL_BACKOFF_HOURS", 24)
    )
    now = timezone.now()

    if not to_email:
        log = EmailDeliveryLog.objects.create(
            recipient=to_email or "(none)",
            template_name=template_name,
            subject=subject,
            status=EmailDeliveryLog.Status.SKIPPED,
            error="empty recipient",
        )
        logger.warning("Alert email skipped: empty recipient (%s)", template_name)
        return log

    # ---- Failure backoff (exponential by consecutive failures) ----
    last_failed = (
        EmailDeliveryLog.objects.filter(
            recipient=to_email,
            template_name=template_name,
            status=EmailDeliveryLog.Status.FAILED,
        )
        .order_by("-created_at")
        .first()
    )
    consecutive_failures = 0
    if last_failed is not None:
        last_success = (
            EmailDeliveryLog.objects.filter(
                recipient=to_email,
                template_name=template_name,
                status=EmailDeliveryLog.Status.SENT,
            )
            .order_by("-created_at")
            .first()
        )
        failures = EmailDeliveryLog.objects.filter(
            recipient=to_email,
            template_name=template_name,
            status=EmailDeliveryLog.Status.FAILED,
        )
        if last_success is not None:
            failures = failures.filter(created_at__gt=last_success.created_at)
        consecutive_failures = failures.count()

        window_hours = min(base_backoff * (2 ** (consecutive_failures - 1)), MAX_BACKOFF_HOURS)
        retry_at = last_failed.created_at + timedelta(hours=window_hours)
        if retry_at > now:
            log = EmailDeliveryLog.objects.create(
                recipient=to_email,
                template_name=template_name,
                subject=subject,
                status=EmailDeliveryLog.Status.SKIPPED,
                attempt=consecutive_failures + 1,
                error=(
                    f"backoff until {retry_at:%Y-%m-%d %H:%M} "
                    f"({consecutive_failures} consecutive failure(s))"
                ),
            )
            logger.info(
                "Alert email %s → %s held in backoff until %s",
                template_name,
                to_email,
                retry_at.isoformat(),
            )
            return log

    # ---- Daily budget (only successful sends count) ----
    sent_today = EmailDeliveryLog.objects.filter(
        recipient=to_email,
        template_name=template_name,
        status=EmailDeliveryLog.Status.SENT,
        created_at__date=now.date(),
    ).count()
    if sent_today >= budget:
        log = EmailDeliveryLog.objects.create(
            recipient=to_email,
            template_name=template_name,
            subject=subject,
            status=EmailDeliveryLog.Status.SKIPPED,
            attempt=consecutive_failures + 1,
            error=f"daily budget {budget} reached ({sent_today} sent today)",
        )
        logger.info(
            "Alert email %s → %s throttled: daily budget %d reached",
            template_name,
            to_email,
            budget,
        )
        return log

    # ---- Send ----
    try:
        sent = send_html_email(
            subject=subject,
            to_email=to_email,
            template_name=template_name,
            context=context,
        )
        error = ""
    except Exception as exc:  # pragma: no cover - send_html_email is fail_silently, defensive
        sent = 0
        error = f"{type(exc).__name__}: {exc}"

    if sent == 1:
        status = EmailDeliveryLog.Status.SENT
    else:
        status = EmailDeliveryLog.Status.FAILED
        error = error or "send returned 0 (fail_silently swallowed a delivery error)"

    log = EmailDeliveryLog.objects.create(
        recipient=to_email,
        template_name=template_name,
        subject=subject,
        status=status,
        attempt=consecutive_failures + 1,
        error=error[:1000],
    )
    if status == EmailDeliveryLog.Status.FAILED:
        logger.error(
            "Alert email %s → %s failed (attempt %d): %s",
            template_name,
            to_email,
            log.attempt,
            error,
        )
    return log
