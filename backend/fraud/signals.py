"""Auto-scan newly created rooms.

Runs the fraud detector on every room at creation time so a listing is
already risk-scored before anyone sees it. Landlord gets a notification (and
an email) when their listing is flagged.

The scan is deliberately *not* re-run on update: re-scanning on every PATCH
would be noisy and expensive; the landlord can re-scan explicitly (or an
admin can) via ``POST /fraud/rooms/{id}/scan/`` or the ``scan_rooms`` command.

The scan runs through the Celery task queue (``fraud.tasks.scan_room``), which
is eager-mode locally (no broker) so behaviour is identical without Redis —
and the dispatch is wrapped in try/except so a detector failure can never
break room creation (the listing always saves; the scan is best-effort).
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from notifications.utils import create_notification
from rooms.models import Room

from .models import FraudReport

logger = logging.getLogger(__name__)

# Only medium/high flags warrant interrupting the landlord; low-severity
# findings are informational and shown in the dashboard instead.
_ALERT_SEVERITIES = (FraudReport.Severity.MEDIUM, FraudReport.Severity.HIGH)


@receiver(post_save, sender=Room)
def scan_room_on_create(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        from .tasks import scan_room as scan_room_task

        scan_room_task.delay(instance.pk)
    except Exception:  # pragma: no cover - defensive; never break room creation
        logger.exception(
            "Fraud scan dispatch failed for room %s; listing saved anyway.", instance.pk
        )


def notify_fraud_flag(room, report):
    """Send the landlord an in-app notification + email for a flagged listing.

    Extracted so both the Celery task and the scan endpoint can share it.
    """
    if not (report.is_flagged and report.severity in _ALERT_SEVERITIES):
        return
    create_notification(
        user=room.owner,
        notification_type="fraud_flag",
        title="Listing flagged for review",
        message=(
            f"Your listing '{room.title}' was flagged by our fraud "
            f"detection ({report.severity} risk). Please review it."
        ),
        action_url=f"/rooms/{room.pk}",
    )
    from notifications.emails import send_html_email

    send_html_email(
        subject=f"Rentora: your listing '{room.title}' was flagged",
        to_email=room.owner.email,
        template_name="fraud_flag",
        context={
            "user": room.owner,
            "room": room,
            "severity": report.get_severity_display(),
            "score": report.score,
            "signals": report.signals.all(),
        },
    )
