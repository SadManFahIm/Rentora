"""Celery task — daily saved-search match alerts (Phase 10, Search v2)."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def check_saved_searches() -> dict:
    """Alert each user about rooms matching their saved searches since the
    last check. Runs daily via Celery beat; deduped naturally because each
    search's ``last_checked_at`` advances after every run (retried crons
    simply find nothing new)."""
    from django.utils import timezone

    from notifications.models import Notification
    from notifications.utils import create_notification

    from .models import SavedSearch
    from .services import find_new_matches

    checked = 0
    alerted = 0
    now = timezone.now()

    for saved_search in SavedSearch.objects.select_related("user"):
        matches = find_new_matches(saved_search)
        saved_search.last_checked_at = now
        saved_search.save(update_fields=["last_checked_at"])
        checked += 1
        if not matches:
            continue

        area = saved_search.filters.get("area") or "your area"
        names = ", ".join(m.title for m in matches[:3])
        more = f" and {len(matches) - 3} more" if len(matches) > 3 else ""
        create_notification(
            user=saved_search.user,
            notification_type=Notification.Type.SAVED_SEARCH_MATCH,
            title=f"New rooms in {saved_search.name}",
            message=f"{len(matches)} new room(s) found in {area}: {names}{more}",
            action_url="/rooms",
        )
        alerted += 1

    logger.info("Saved-search digest: checked %d search(es), %d alert(s)", checked, alerted)
    return {"checked": checked, "alerted": alerted}
