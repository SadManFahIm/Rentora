from django.apps import AppConfig
from django.conf import settings


class SavedsearchesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "savedsearches"

    def ready(self):
        """Dispatch the AI matcher on room create / price change.

        Runs through the Celery queue (eager in dev/CI, async with a broker)
        and is wrapped defensively so a matching hiccup can never break room
        creation — the listing always saves.
        """
        if not getattr(settings, "SAVED_SEARCH_AI_MATCHING_ENABLED", True):
            return

        import logging

        from django.db.models.signals import post_save
        from django.dispatch import receiver

        from rooms.models import Room

        logger = logging.getLogger(__name__)

        @receiver(post_save, sender=Room)
        def dispatch_room_event(sender, instance, created, **kwargs):
            # Only events that could change matching: new rooms, and rooms
            # whose price changed (stashed by rooms/signals.py pre-save).
            if not created:
                previous = getattr(instance, "_pre_save_price", None)
                if previous is None or previous == instance.price:
                    return
            try:
                from .tasks import match_room_event

                match_room_event.delay(instance.pk, created)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Saved-search matcher dispatch failed for room %s", instance.pk)
