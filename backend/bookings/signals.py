"""Signal handlers that emit notifications on booking/review lifecycle events.

Wired up in :meth:`bookings.apps.BookingsConfig.ready`. Kept separate from
``models.py`` (which owns the room-rating recalculation signals) so the
notification side effects are easy to locate and reason about.
"""

from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.models import Notification
from notifications.utils import create_notification

from .models import Booking, Review

# Client-side route the booking notifications deep-link to.
_BOOKING_ACTION_URL = "/dashboard"


@receiver(pre_save, sender=Booking)
def _capture_previous_booking_status(sender, instance: Booking, **kwargs) -> None:
    """Stash the persisted status on the instance before it is overwritten.

    ``post_save`` cannot tell an approve/reject/cancel apart from any other
    save without knowing the prior value, so we look it up once here and hang
    it on the in-memory instance as ``_previous_status``.
    """
    if instance.pk:
        previous = (
            Booking.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )
        instance._previous_status = previous
    else:
        instance._previous_status = None


@receiver(post_save, sender=Booking)
def notify_on_booking_change(sender, instance: Booking, created: bool, **kwargs) -> None:
    """Notify the relevant party when a booking is created or transitions.

    * created            → room owner  ("New booking request …")
    * → approved         → tenant       ("… has been approved!")
    * → rejected         → tenant       ("… was rejected")
    * → cancelled        → room owner   ("… was cancelled")
    """
    room = instance.room
    room_title = room.title

    if created:
        create_notification(
            user=room.owner,
            notification_type=Notification.Type.BOOKING_REQUEST,
            title="New booking request",
            message=f"New booking request for {room_title}.",
            action_url=_BOOKING_ACTION_URL,
        )
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status:
        # Nothing status-related changed (e.g. agreement_signed/notes edit).
        return

    if instance.status == Booking.Status.APPROVED:
        create_notification(
            user=instance.tenant,
            notification_type=Notification.Type.BOOKING_APPROVED,
            title="Booking approved",
            message=f"Your booking for {room_title} has been approved!",
            action_url=_BOOKING_ACTION_URL,
        )
    elif instance.status == Booking.Status.REJECTED:
        create_notification(
            user=instance.tenant,
            notification_type=Notification.Type.BOOKING_REJECTED,
            title="Booking rejected",
            message=f"Your booking for {room_title} was rejected.",
            action_url=_BOOKING_ACTION_URL,
        )
    elif instance.status == Booking.Status.CANCELLED:
        create_notification(
            user=room.owner,
            notification_type=Notification.Type.BOOKING_CANCELLED,
            title="Booking cancelled",
            message=f"Booking for {room_title} was cancelled.",
            action_url=_BOOKING_ACTION_URL,
        )


@receiver(post_save, sender=Review)
def notify_on_review_created(sender, instance: Review, created: bool, **kwargs) -> None:
    """Notify the room owner when a new review is posted on their room."""
    if not created:
        return

    room = instance.room
    create_notification(
        user=room.owner,
        notification_type=Notification.Type.NEW_REVIEW,
        title="New review",
        message=f"New {instance.rating}★ review on {room.title}.",
        action_url=f"/rooms/{room.pk}",
    )
