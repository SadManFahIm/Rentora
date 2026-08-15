import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from rooms.models import RoomImage

logger = logging.getLogger(__name__)


@receiver(post_save, sender=RoomImage)
def moderate_room_image(sender, instance, created, **kwargs):
    """Assess every newly uploaded listing photo (Phase 12.5).

    Runs synchronously but is deliberately cheap (cached pHash + prefix
    lookup); failures are swallowed so moderation can never break an image
    upload. An admin queue is where flagged photos are reviewed.
    """
    if not created:
        return
    from .services import record_listing_photo_moderation

    try:
        record_listing_photo_moderation(instance)
    except Exception:  # pragma: no cover - moderation must never break uploads
        logger.exception("Photo moderation failed for RoomImage %s", instance.pk)
