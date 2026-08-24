"""AI Intelligence Layer — Phase 18.1 Celery tasks.

Provides:
- Provider health aggregation (periodic)
- Execution log cleanup (periodic)
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="ai_intelligence.update_provider_health")
def update_provider_health(hours: int = 1) -> dict:
    """Aggregate AI execution logs into ProviderHealth records.

    Called periodically by Celery beat. Aggregates execution logs
    from the last `hours` into ProviderHealth summary records.
    """
    from .services import update_provider_health as _update

    try:
        updated = _update(hours=hours)
        logger.info("Provider health updated: %d records", updated)
        return {"updated": updated, "status": "success"}
    except Exception as exc:
        logger.exception("Provider health update failed")
        return {"updated": 0, "status": "error", "error": str(exc)}


@shared_task(name="ai_intelligence.purge_old_execution_logs")
def purge_old_execution_logs() -> dict:
    """Delete AI execution logs older than retention period.

    Uses AI_EXECUTION_LOG_RETENTION_DAYS setting (default 90 days).
    """
    from .models import AIExecutionLog

    retention_days = getattr(settings, "AI_EXECUTION_LOG_RETENTION_DAYS", 90)
    cutoff = timezone.now() - timedelta(days=retention_days)

    try:
        count, _ = AIExecutionLog.objects.filter(created_at__lt=cutoff).delete()
        logger.info("Purged %d old AI execution logs (older than %d days)", count, retention_days)
        return {"deleted": count, "status": "success"}
    except Exception as exc:
        logger.exception("Execution log purge failed")
        return {"deleted": 0, "status": "error", "error": str(exc)}
