"""Celery tasks — analytics (Phase 15, C6).

``generate_market_report`` — the weekly rental market report: writes the
price snapshot for the current week and emails opted-in subscribers. Runs via
Celery beat (Mondays 06:00 Asia/Dhaka); with no broker configured (local
dev/CI) tasks run eagerly/synchronously, exercising the same code path.
"""

from __future__ import annotations

import logging

from celery import shared_task

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
