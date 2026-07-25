"""Advance/recurring payment schedule generation.

Generates one `PaymentSchedule` row per monthly rent installment for the
duration of a booking's lease, so tenants and landlords can see the full
advance payment plan as soon as a booking is approved — not just the
payments that have actually been made so far.
"""

from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from bookings.models import Booking
    from payments.models import PaymentSchedule


def _add_one_month(d: datetime.date) -> datetime.date:
    """Calendar-correct "same day next month" (clamped to the shorter month)."""
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _lease_end(booking: "Booking") -> datetime.date:
    if booking.check_out:
        return booking.check_out

    month = booking.check_in.month + settings.DEFAULT_LEASE_SCHEDULE_MONTHS
    year = booking.check_in.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(booking.check_in.day, calendar.monthrange(year, month)[1])
    return booking.check_in.replace(year=year, month=month, day=day)


def generate_payment_schedule(booking: "Booking") -> list["PaymentSchedule"]:
    """Create the monthly installment schedule for an approved booking.

    Idempotent: a booking that already has schedule rows is left untouched,
    so this can safely be called every time a booking is (re-)saved as
    approved without ever duplicating entries.
    """
    from payments.models import PaymentSchedule

    if booking.payment_schedules.exists():
        return []

    lease_end = _lease_end(booking)

    entries = []
    due_date = booking.check_in
    while due_date < lease_end:
        entries.append(
            PaymentSchedule(booking=booking, due_date=due_date, amount=booking.monthly_rent)
        )
        due_date = _add_one_month(due_date)

    if not entries:
        return []

    return PaymentSchedule.objects.bulk_create(entries)
