"""Shared rent-reminder logic (command + Celery task both call this)."""

from __future__ import annotations

import calendar
import datetime

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


def send_payment_reminders() -> dict[str, int | str]:
    """Notify tenants whose next monthly rent is due in ``REMINDER_LEAD_DAYS``.

    Returns ``{"sent": n, "due_date": "YYYY-MM-DD"}``. Idempotent per
    tenant/room/day (a retried run never double-notifies).
    """
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

        # Avoid re-sending the same reminder if the command runs more than
        # once on the same day (e.g. a retried cron invocation).
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

    return {"sent": sent, "due_date": str(target_due_date)}
