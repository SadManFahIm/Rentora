"""Keep listing badges in sync with the owner's KYC (nid_verified) status.

``Room.verified`` is the badge the frontend renders on cards and the modal.
It is intentionally admin-overridable per listing, but its *source of truth*
is the owner's ``nid_verified``: when an admin approves a landlord's KYC, all
of that landlord's listings should immediately show the verified badge, and
if verification is ever revoked, the badges must come off too.

Implemented as a pre_save stash + post_save compare (the same pattern as
``bookings/signals.py``'s status tracker) so a save that doesn't touch
``nid_verified`` never triggers a needless UPDATE of the owner's rooms.

Known bypass: ``QuerySet.update()`` / ``bulk_update()`` do not fire model
signals, so a bulk KYC change made that way will not flip badges. Use
instance.save() (the Django admin form.save() path) for KYC changes.
"""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

User = get_user_model()


@receiver(pre_save, sender=User)
def _capture_previous_nid_verified(sender, instance, **kwargs) -> None:
    """Stash the persisted ``nid_verified`` before it is overwritten."""
    if instance.pk:
        instance._previous_nid_verified = (
            User.objects.filter(pk=instance.pk).values_list("nid_verified", flat=True).first()
        )
    else:
        instance._previous_nid_verified = None


@receiver(post_save, sender=User)
def sync_room_verification_on_kyc_change(sender, instance, created, **kwargs) -> None:
    """Propagate a KYC change to the landlord's listings (badge on/off)."""
    if created:
        return
    previous = getattr(instance, "_previous_nid_verified", None)
    if previous == instance.nid_verified:
        return

    from rooms.models import Room

    Room.objects.filter(owner=instance).update(verified=instance.nid_verified)
