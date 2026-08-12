from django.apps import AppConfig


class RoomsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rooms"

    def ready(self):
        """Import signal handlers (price history) so they register."""
        from . import signals  # noqa: F401
