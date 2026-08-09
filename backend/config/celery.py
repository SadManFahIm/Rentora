"""Celery application instance for Rentora.

Broker & execution mode
-----------------------
The broker URL comes from the ``CELERY_BROKER_URL`` env var. When it is empty
(the default — no Redis running locally), tasks run in **eager mode**: every
``.delay()`` executes synchronously in the calling process, so local dev and
the test suite work with zero extra services while exercising the exact same
task code paths.

Production sets ``CELERY_BROKER_URL=redis://...`` (see prod.py), which flips
eager mode off automatically and hands tasks to a real worker. Beat schedules
also only take effect with a real broker.

Run locally with a broker::

    celery -A config worker -l info
    celery -A config beat -l info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("rentora")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Convenience export so `from config.celery import app` reads naturally
# alongside the classic `config.celery` module reference.
__all__ = ["app"]
