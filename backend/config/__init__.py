# Celery is auto-discovered via `config.celery:app`; importing it here makes
# `celery -A config` resolve the app without an explicit --app flag.
from .celery import app as celery_app

__all__ = ["celery_app"]
