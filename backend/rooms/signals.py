"""Room lifecycle signals (Phase 11+ — price-drop intelligence).

Records every price change into ``RoomPriceHistory`` so saved-search price-drop
alerts and landlord price history have a source of truth. A pre-save stash
captures the previous price (same pattern as ``users/signals.py``) and the
post-save handler writes a history row only when the price actually changed —
never on a no-op save.

The saved-search *matching* dispatch on room create/price-change lives in
``savedsearches/apps.py`` (it's a consumer of this app, not a room concern).
"""

from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Room, RoomPriceHistory


@receiver(pre_save, sender=Room)
def stash_previous_price(sender, instance, **kwargs) -> None:
    """Remember the row's previous price before the save overwrites it."""
    instance._pre_save_price = None
    if instance.pk is None:
        return
    previous = Room.objects.filter(pk=instance.pk).values_list("price", flat=True).first()
    instance._pre_save_price = previous


@receiver(post_save, sender=Room)
def record_price_history(sender, instance, created, **kwargs) -> None:
    """Write a history row on creation and on any actual price change."""
    if created:
        RoomPriceHistory.objects.create(room=instance, price=instance.price)
        return
    previous = getattr(instance, "_pre_save_price", None)
    if previous is not None and previous != instance.price:
        RoomPriceHistory.objects.create(room=instance, price=instance.price)
