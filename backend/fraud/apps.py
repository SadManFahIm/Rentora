from django.apps import AppConfig


class FraudConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fraud"

    def ready(self) -> None:
        """Import signal handlers so new rooms are scanned automatically."""
        from . import signals  # noqa: F401
