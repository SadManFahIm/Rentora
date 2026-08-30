from django.apps import AppConfig


class PropertyIntelligenceConfig(AppConfig):
    """Phase 19.1 — composite, explainable Property Intelligence Score."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "property_intelligence"
    verbose_name = "Property Intelligence"

    def ready(self) -> None:
        from . import signals  # noqa: F401
