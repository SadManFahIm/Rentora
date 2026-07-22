from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bookings"

    def ready(self) -> None:
        """Import signal handlers so booking/review events emit notifications."""
        from . import signals  # noqa: F401
