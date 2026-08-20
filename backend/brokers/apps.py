from django.apps import AppConfig


class BrokersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "brokers"
    verbose_name = "Broker Network"

    def ready(self):
        from . import signals  # noqa: F401  (register booking→commission receivers)
