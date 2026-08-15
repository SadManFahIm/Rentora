from django.apps import AppConfig


class ModerationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "moderation"
    verbose_name = "Content Moderation"

    def ready(self):
        # Importing registers the RoomImage post-save moderation hook.
        from . import signals  # noqa: F401
