"""Property Intelligence cache invalidation (Phase 19.1).

The composite score is cached under ``property-intelligence:{room_id}:{config
signature}`` (see ``engine``). Any material change to a listing's source
signals must expire that entry so the next read recomputes. Hot demand paths
(views/wishlists/bookings) are deliberately *not* signalled — the short TTL
self-refreshes them, keeping write-heavy traffic off the cache invalidation
path.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

_VERIFICATION_FIELDS = ("nid_verified", "tenant_verified")


def _invalidate(room_id: int) -> None:
    from .engine import invalidate_for_room

    invalidate_for_room(room_id)


@receiver(post_save, sender="rooms.Room")
def _room_saved(sender, instance, **kwargs) -> None:
    _invalidate(instance.pk)


@receiver(post_save, sender="rooms.RoomImage")
def _image_saved(sender, instance, **kwargs) -> None:
    _invalidate(instance.room_id)


@receiver(post_delete, sender="rooms.RoomImage")
def _image_deleted(sender, instance, **kwargs) -> None:
    _invalidate(instance.room_id)


@receiver(pre_save, sender="users.User")
def _stash_owner_verification(sender, instance, **kwargs) -> None:
    instance._pre_verification = None
    if instance.pk is None:
        return
    from django.contrib.auth import get_user_model

    User = get_user_model()
    previous = User.objects.filter(pk=instance.pk).values_list(*_VERIFICATION_FIELDS).first()
    instance._pre_verification = previous


@receiver(post_save, sender="users.User")
def _owner_verification_changed(sender, instance, created, **kwargs) -> None:
    """Expire scores for an owner's listings when KYC flags actually change."""
    previous = getattr(instance, "_pre_verification", None)
    current = tuple(getattr(instance, f, None) for f in _VERIFICATION_FIELDS)
    if created or previous is None or previous != current:
        from rooms.models import Room

        # Cap the burst so a pathological owner can't stall a hot save.
        for room_id in Room.objects.filter(owner=instance).values_list("id", flat=True)[:100]:
            _invalidate(room_id)
