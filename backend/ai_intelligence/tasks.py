"""AI Intelligence Layer — Phase 18.1 + 18.3 + 18.4 Celery tasks.

Provides:
- Provider health aggregation (periodic)
- Execution log cleanup (periodic)
- Evaluation run execution (on-demand)
- Stale evaluation cleanup (periodic)
- Alert rule evaluation (periodic, Phase 18.4)
- Dashboard cache warm-up (periodic, Phase 18.4)
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


# ---------------------------------------------------------------------------
# Phase 18.3 — Evaluation Framework Tasks
# ---------------------------------------------------------------------------


@shared_task(name="ai_intelligence.execute_evaluation_run")
def execute_evaluation_run_task(run_id: int) -> dict:
    """Execute an evaluation run as a Celery background job.

    This task is idempotent — re-running a completed or failed run
    will re-execute from scratch.
    """
    from .services import execute_evaluation_run

    try:
        result = execute_evaluation_run(run_id)
        logger.info("Evaluation run %d completed: %s", run_id, result.get("status"))
        return result
    except Exception as exc:
        logger.exception("Evaluation run %d failed", run_id)
        return {"status": "error", "run_id": run_id, "error": str(exc)}


@shared_task(name="ai_intelligence.cancel_stale_evaluation_runs")
def cancel_stale_evaluation_runs() -> dict:
    """Cancel evaluation runs that have been running longer than their timeout.

    Called periodically by Celery beat to prevent stuck evaluations.
    """
    from .models import EvaluationRun

    try:
        stale_cutoff = timezone.now() - timedelta(seconds=3600)
        stale_runs = EvaluationRun.objects.filter(
            status="running",
            started_at__lt=stale_cutoff,
        )
        count = 0
        for run in stale_runs:
            run.status = "cancelled"
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at"])
            count += 1
            logger.warning("Cancelled stale evaluation run %d", run.pk)
        return {"cancelled": count, "status": "success"}
    except Exception as exc:
        logger.exception("Stale evaluation cleanup failed")
        return {"cancelled": 0, "status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Phase 18.4 — Alerts + Dashboard
# ---------------------------------------------------------------------------


@shared_task(name="ai_intelligence.evaluate_alert_rules")
def evaluate_alert_rules_task() -> dict:
    """Evaluate every enabled AI alert rule.

    Called periodically by Celery beat. Triggered alerts notify admins and
    are written to the audit log by the alert service.
    """
    from .alerts import evaluate_all_rules

    try:
        result = evaluate_all_rules()
        logger.info("Alert evaluation complete: %s", result.get("counts"))
        return result
    except Exception as exc:
        logger.exception("Alert rule evaluation failed")
        return {"evaluated": 0, "status": "error", "error": str(exc)}


@shared_task(name="ai_intelligence.warm_dashboard_cache")
def warm_dashboard_cache() -> dict:
    """Pre-compute the AI dashboard aggregates into cache.

    Runs a few seconds after ``evaluate_alert_rules_task`` in the beat
    schedule so the admin dashboard's first render does not pay the full
    aggregation cost synchronously.
    """
    from . import dashboard

    try:
        dashboard.get_ai_summary()
        dashboard.get_feature_health_list()
        dashboard.get_model_health()
        dashboard.get_provider_health()
        dashboard.get_cost_dashboard()
        dashboard.get_performance_dashboard()
        dashboard.get_error_dashboard()
        dashboard.get_quality_dashboard()
        dashboard.get_prompt_health()
        dashboard.get_drift_status()
        logger.info("AI dashboard cache warmed")
        return {"warmed": True, "status": "success"}
    except Exception as exc:
        logger.exception("AI dashboard cache warm-up failed")
        return {"warmed": False, "status": "error", "error": str(exc)}
