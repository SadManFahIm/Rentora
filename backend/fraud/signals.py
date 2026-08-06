"""Auto-scan newly created rooms.

Runs the fraud detector on every room at creation time so a listing is
already risk-scored before anyone sees it. Landlord gets a notification when
their listing is flagged.

The scan is deliberately *not* re-run on update: re-scanning on every PATCH
would be noisy and expensive; the landlord can re-scan explicitly (or an
admin can) via ``POST /fraud/rooms/{id}/scan/`` or the ``scan_rooms`` command.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from notifications.utils import create_notification
from rooms.models import Room

from .models import FraudReport
from .services.detectors import run_scan

# Only medium/high flags warrant interrupting the landlord; low-severity
# findings are informational and shown in the dashboard instead.
_ALERT_SEVERITIES = (FraudReport.Severity.MEDIUM, FraudReport.Severity.HIGH)


@receiver(post_save, sender=Room)
def scan_room_on_create(sender, instance, created, **kwargs):
    if not created:
        return

    report = run_scan(instance)
    if report.is_flagged and report.severity in _ALERT_SEVERITIES:
        create_notification(
            user=instance.owner,
            notification_type="fraud_flag",
            title="Listing flagged for review",
            message=(
                f"Your listing '{instance.title}' was flagged by our fraud "
                f"detection ({report.severity} risk). Please review it."
            ),
            action_url=f"/rooms/{instance.pk}",
        )
