"""Booking → broker-commission wiring.

A verified broker whose referral code was used on a booking earns a
commission when that booking is APPROVED. Idempotent by booking id, so
re-saving an already-approved booking never double-pays.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from bookings.models import Booking
from monetization.services.commissions import create_commission
from notifications.models import Notification
from notifications.utils import create_notification


@receiver(post_save, sender=Booking)
def on_booking_approved(sender, instance: Booking, created: bool, **kwargs) -> None:
    if created or instance.status != Booking.Status.APPROVED:
        return
    if getattr(instance, "_previous_status", None) == Booking.Status.APPROVED:
        return

    broker = instance.broker_referral
    if broker is None or not broker.is_verified():
        return

    commission = create_commission(
        kind="broker_booking",
        recipient=broker.user,
        gross_amount=instance.monthly_rent,
        scope="broker",
        source=instance,
        idempotency_key=f"broker-booking-{instance.pk}",
        detail={
            "room_id": instance.room_id,
            "booking_id": instance.pk,
            "tenant_id": instance.tenant_id,
        },
    )
    if commission.status == "pending":
        from monetization.services.ledger import record_entry

        record_entry(
            entry_type="commission_broker",
            scope="broker",
            user=broker.user,
            gross=instance.monthly_rent,
            platform_amount=0,
            partner_amount=commission.amount,
            source=instance,
            idempotency_key=f"broker-booking-ledger-{instance.pk}",
            detail={"commission_id": commission.pk},
        )
        create_notification(
            user=broker.user,
            notification_type=Notification.Type.COMMISSION_EARNED,
            title="Commission earned",
            message=f"You earned a {commission.amount} BDT commission on an approved booking.",
            action_url="/dashboard?tab=broker",
        )
