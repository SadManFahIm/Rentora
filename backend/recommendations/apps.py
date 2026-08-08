from django.apps import AppConfig


class RecommendationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "recommendations"

    def ready(self) -> None:
        """Import signal handlers so wishlist/booking events log UserActivity."""
        from . import signals  # noqa: F401
