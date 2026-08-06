"""Send a reminder notification for rent that's due in 3 days.

Scheduling
----------
No Celery/Celery-beat setup exists in this project yet, so this is a plain
management command meant to be triggered once a day by an external
scheduler. Once Celery is introduced, this same logic should move into a
``@shared_task`` and be scheduled via ``CELERY_BEAT_SCHEDULE``:

    CELERY_BEAT_SCHEDULE = {
        "send-payment-reminders": {
            "task": "payments.tasks.send_payment_reminders",
            "schedule": crontab(hour=9, minute=0),  # once daily at 9am
        },
    }

Until then, run it via a system cron entry (Linux/prod), e.g.:

    0 9 * * * cd /path/to/backend && venv/bin/python manage.py send_payment_reminders

...or Windows Task Scheduler running the equivalent `python manage.py
send_payment_reminders` daily.
"""

import calendar
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.models import Booking
from notifications.models import Notification
from notifications.utils import create_notification
from payments.models import Payment

REMINDER_LEAD_DAYS = 3


def _add_one_month(d: datetime.date) -> datetime.date:
    """Calendar-correct "same day next month" (clamped to the shorter month)."""
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


class Command(BaseCommand):
    help = "Notify tenants whose next monthly rent payment is due in 3 days."

    def handle(self, *args, **options):
        today = timezone.localdate()
        target_due_date = today + datetime.timedelta(days=REMINDER_LEAD_DAYS)

        bookings = Booking.objects.filter(status=Booking.Status.APPROVED).select_related(
            "room", "room__owner", "tenant"
        )

        sent = 0
        for booking in bookings:
            last_payment = (
                Payment.objects.filter(
                    booking=booking,
                    payment_type=Payment.Type.MONTHLY_RENT,
                    status=Payment.Status.SUCCESS,
                )
                .order_by("-created_at")
                .first()
            )
            base_date = last_payment.created_at.date() if last_payment else booking.check_in
            next_due_date = _add_one_month(base_date)

            if next_due_date != target_due_date:
                continue

            # Avoid re-sending the same reminder if the command runs more
            # than once on the same day (e.g. a retried cron invocation).
            already_sent_today = Notification.objects.filter(
                user=booking.tenant,
                notification_type=Notification.Type.PAYMENT_REMINDER,
                created_at__date=today,
                message__contains=booking.room.title,
            ).exists()
            if already_sent_today:
                continue

            create_notification(
                user=booking.tenant,
                notification_type=Notification.Type.PAYMENT_REMINDER,
                title="Rent payment due soon",
                message=f"Rent payment for {booking.room.title} is due in {REMINDER_LEAD_DAYS} days.",
                action_url="/dashboard/bookings",
            )
            sent += 1

        self.stdout.write(
            self.style.SUCCESS(f"Sent {sent} payment reminder(s) for {target_due_date}.")
        )
