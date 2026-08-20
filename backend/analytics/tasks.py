"""Celery tasks — analytics (Phase 15, C6 / Phase 16, Stage 8).

``generate_market_report`` — the weekly rental market report: writes the
price snapshot for the current week and emails opted-in subscribers. Runs via
Celery beat (Mondays 06:00 Asia/Dhaka); with no broker configured (local
dev/CI) tasks run eagerly/synchronously, exercising the same code path.

``purge_expired_events`` — retention job that deletes analytics events older
than ``ANALYTICS_EVENT_RETENTION_DAYS`` (default 365). Runs daily via beat so
the first-party event store stays bounded and GDPR-friendly.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def generate_market_report() -> dict:
    """Generate + persist the weekly market report and email subscribers."""
    from .market_report import generate_report

    try:
        report = generate_report()
    except Exception:  # never take down the beat loop on a data hiccup
        logger.exception("market report generation failed")
        return {"ok": False}
    logger.info(
        "Market report %s generated (%d areas, baseline=%s)",
        report["week_label"],
        len(report["areas"]),
        report["baseline"],
    )
    return {"ok": True, "week_label": report["week_label"], "areas": len(report["areas"])}


@shared_task
def purge_expired_events() -> dict:
    """Delete analytics events older than the retention window (bounded store)."""
    from .models import Event

    retention_days = int(getattr(settings, "ANALYTICS_EVENT_RETENTION_DAYS", 365))
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    try:
        deleted, _ = Event.objects.filter(created_at__lt=cutoff).delete()
    except Exception:  # never take down the beat loop on a data hiccup
        logger.exception("analytics retention purge failed")
        return {"ok": False}
    logger.info(
        "Analytics retention purge removed %d event(s) older than %d days", deleted, retention_days
    )
    return {"ok": True, "deleted": deleted, "retention_days": retention_days}
