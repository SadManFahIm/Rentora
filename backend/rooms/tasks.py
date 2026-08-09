"""Celery tasks for the rooms app — scheduled maintenance."""

from celery import shared_task

from rooms.services import expire_listing_tiers as _expire_listing_tiers


@shared_task
def expire_listing_tiers():
    """Revert paid listing tiers (Featured/Premium) that have expired back to Free.

    Delegates to :func:`rooms.services.expire_listing_tiers` — the same code
    path the ``expire_listings`` management command uses, so a scheduled run
    and a manual run can never drift (both email the owners).
    """
    return _expire_listing_tiers()
