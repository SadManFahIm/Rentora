"""Signal handlers that log UserActivity rows for the recommendation engine.

Wired up in :meth:`recommendations.apps.RecommendationsConfig.ready`. Room
*view* activity is logged by middleware instead (see ``middleware.py``) since
a page view isn't a model-lifecycle event.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from bookings.models import Booking
from wishlist.models import Wishlist

from .models import UserActivity


@receiver(post_save, sender=Wishlist)
def log_wishlist_activity(sender, instance: Wishlist, created: bool, **kwargs) -> None:
    """A wishlist entry is only ever created (never updated) by the toggle
    endpoint, so `created` is the right (and only) moment to log interest —
    removing a room from the wishlist is a signal of *reduced* interest, not
    logged as a positive activity."""
    if not created:
        return

    UserActivity.objects.create(
        user=instance.user,
        room=instance.room,
        activity_type=UserActivity.ActivityType.WISHLIST,
        weight=UserActivity.DEFAULT_WEIGHTS[UserActivity.ActivityType.WISHLIST],
    )


@receiver(post_save, sender=Booking)
def log_booking_activity(sender, instance: Booking, created: bool, **kwargs) -> None:
    """Log a `booking_request` the moment a booking is created, and a
    `booking_approved` the moment it transitions into that status."""
    if created:
        UserActivity.objects.create(
            user=instance.tenant,
            room=instance.room,
            activity_type=UserActivity.ActivityType.BOOKING_REQUEST,
            weight=UserActivity.DEFAULT_WEIGHTS[UserActivity.ActivityType.BOOKING_REQUEST],
        )
        return

    if instance.status == Booking.Status.APPROVED:
        already_logged = UserActivity.objects.filter(
            user=instance.tenant,
            room=instance.room,
            activity_type=UserActivity.ActivityType.BOOKING_APPROVED,
        ).exists()
        if not already_logged:
            UserActivity.objects.create(
                user=instance.tenant,
                room=instance.room,
                activity_type=UserActivity.ActivityType.BOOKING_APPROVED,
                weight=UserActivity.DEFAULT_WEIGHTS[UserActivity.ActivityType.BOOKING_APPROVED],
            )
