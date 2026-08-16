"""Transparent tenant trust signals (Tier 3).

Phase 12 built identity signals (``tenant_verified`` / ``nid_verified``).
This module adds the **behavioral** side: signals backed by real platform
data, not guesses — exactly the "completed bookings" the badge should show
next to identity verification.

Every signal is a fact the platform can prove:

* ``tenant_verified`` — identity verified through the Tenant KYC review.
* ``nid_verified`` — identity verified through the landlord KYC review.
* ``completed_bookings`` — approved bookings whose stay actually ended
  (security deposit refunded, or the check-out date passed).
* ``profile_complete`` — phone + avatar + full name on file.

No internal fraud scores are ever exposed here.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Q


def completed_bookings_count(user) -> int:
    """Approved bookings that have genuinely completed.

    A booking counts as completed only when the stay ended: the security
    deposit was refunded (the landlord closed the deposit cycle) or the
    check-out date has passed. Pending/approved-in-progress bookings never
    count — the signal must be earned, not implied.
    """
    from bookings.models import Booking

    today = date.today()
    return (
        Booking.objects.filter(tenant=user, status=Booking.Status.APPROVED)
        .filter(Q(security_deposit_refunded=True) | Q(check_out__lt=today))
        .count()
    )


def trust_signals(user) -> dict:
    """The public, data-backed trust signal set for one user."""
    if user is None:
        return {
            "tenant_verified": False,
            "nid_verified": False,
            "completed_bookings": 0,
            "profile_complete": False,
        }
    full_name = user.get_full_name()
    return {
        "tenant_verified": bool(getattr(user, "tenant_verified", False)),
        "nid_verified": bool(getattr(user, "nid_verified", False)),
        "completed_bookings": completed_bookings_count(user),
        "profile_complete": bool(user.phone and getattr(user, "avatar", None) and full_name),
    }
