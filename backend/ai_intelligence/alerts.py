"""AI Intelligence Alerts (Phase 18.4) — rule evaluation + lifecycle services.

Rules watch existing Phase 18.1 telemetry / Phase 18.3 evaluation / Phase 17
drift measurements against a threshold and produce ``AIAlert`` records when
breached consistently.

Anti-noise design:
- **consecutive_checks** — a rule only fires after the metric breaches for
  ``consecutive_checks`` consecutive evaluation runs (tracked by
  ``AIAlertRule.breach_count``, reset to 0 as soon as the metric recovers).
- **cooldown_minutes** — after an alert fires, the same (rule, scope) cannot
  re-fire until the cooldown window has passed.
- **dedup_key** — one open (triggered/acknowledged) alert per scope; new
  breaches during that alert's lifetime are folded into ``breach_count`` on
  the existing alert instead of creating duplicates.

Metric ``None`` (no telemetry in scope) never triggers — it keeps ``breach_count``
at 0 so a data gap cannot accumulate a false breach streak.

All cost figures are ESTIMATED (from ``AIExecutionLog.estimated_cost_usd``).
Every created/transitioned alert is written to the audit log.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Q, Sum
from django.utils import timezone

from audit.services import log_action
from notifications.utils import create_notification

from .models import AIAlert, AIAlertRule, AIExecutionLog, EvaluationRun

logger = logging.getLogger(__name__)

User = get_user_model()

# 24h in minutes — used for the ``daily_cost`` metric look-back.
DAY_MINUTES = 1440


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def _execution_scope(rule: AIAlertRule):
    """AIExecutionLog queryset filtered to the rule's scope + look-back window."""
    duration = (
        DAY_MINUTES if rule.metric == AIAlertRule.Metric.DAILY_COST else rule.duration_minutes
    )
    since = timezone.now() - timezone.timedelta(minutes=int(duration or 1))
    qs = AIExecutionLog.objects.filter(created_at__gte=since)
    if rule.feature_id:
        qs = qs.filter(feature_key=rule.feature.feature_id)
    if rule.provider:
        qs = qs.filter(provider=rule.provider)
    if rule.model_name:
        qs = qs.filter(model_name=rule.model_name)
    return qs


def _latency_percentile(qs: Any, pct: float) -> int:
    values = list(qs.order_by("-created_at").values_list("latency_ms", flat=True)[:20000])
    if not values:
        return 0
    ordered = sorted(values)
    k = max(1, round(pct / 100 * len(ordered)))
    return int(ordered[min(k, len(ordered)) - 1])


def compute_metric_value(rule: AIAlertRule) -> float | None:
    """Compute the current value of a rule's metric in its scope.

    Returns ``None`` when the scope has no data to evaluate (never triggers).
    Latency/cost use millisecond / USD units; rates are percentages 0-100.
    """
    metric = rule.metric

    if metric == AIAlertRule.Metric.DRIFT_BREACH:
        from ml_models.models import DriftMetric, ModelVersion

        qs = DriftMetric.objects.filter(threshold_breached=True)
        if rule.model_name:
            model_ids = ModelVersion.objects.filter(name=rule.model_name).values("id")
            qs = qs.filter(model_version_id__in=model_ids)
        return float(qs.count())

    if metric == AIAlertRule.Metric.EVALUATION_SCORE:
        runs = EvaluationRun.objects.filter(status="completed")
        if rule.feature_id:
            runs = runs.filter(feature=rule.feature)
        if rule.model_name:
            runs = runs.filter(model_name=rule.model_name)
        if rule.provider:
            runs = runs.filter(provider=rule.provider)
        latest = runs.order_by("-created_at").first()
        return float(latest.score) if latest else None

    window = _execution_scope(rule)
    total = window.count()

    if metric == AIAlertRule.Metric.ERROR_RATE:
        if not total:
            return None
        failed = window.filter(status__in=["failure", "timeout"]).count()
        return round(failed / total * 100, 4)
    if metric == AIAlertRule.Metric.TIMEOUT_RATE:
        if not total:
            return None
        timeouts = window.filter(status="timeout").count()
        return round(timeouts / total * 100, 4)
    if metric == AIAlertRule.Metric.FALLBACK_RATE:
        if not total:
            return None
        fallbacks = window.filter(is_fallback=True).count()
        return round(fallbacks / total * 100, 4)
    if metric == AIAlertRule.Metric.SUCCESS_RATE:
        if not total:
            return None
        success = window.filter(status="success").count()
        return round(success / total * 100, 4)
    if metric == AIAlertRule.Metric.AVG_LATENCY:
        if not total:
            return None
        return round(float(window.aggregate(a=Avg("latency_ms"))["a"] or 0), 2)
    if metric == AIAlertRule.Metric.P95_LATENCY:
        if not total:
            return None
        return float(_latency_percentile(window, 95))
    if metric == AIAlertRule.Metric.DAILY_COST:
        if not total:
            return None
        cost = window.aggregate(c=Sum("estimated_cost_usd"))["c"] or 0
        return round(float(cost), 6)
    if metric == AIAlertRule.Metric.COST_PER_EXECUTION:
        if not total:
            return None
        cost = window.aggregate(c=Sum("estimated_cost_usd"))["c"] or 0
        return round(float(cost) / total, 8)
    return None


def _is_breach(rule: AIAlertRule, value: float) -> bool:
    threshold = rule.threshold_value
    op = rule.operator
    if op == AIAlertRule.Operator.GT:
        return value > threshold
    if op == AIAlertRule.Operator.GTE:
        return value >= threshold
    if op == AIAlertRule.Operator.LT:
        return value < threshold
    if op == AIAlertRule.Operator.LTE:
        return value <= threshold
    return False


def _scope_key(rule: AIAlertRule) -> str:
    """Normalized scope for dedup/cooldown (feature, provider, model)."""
    feature = rule.feature.feature_id if rule.feature_id else ""
    return f"{feature}::{rule.provider}::{rule.model_name}"


def _dedup_key(rule: AIAlertRule) -> str:
    payload = f"{rule.rule_key}|{_scope_key(rule)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Triggering / anti-noise
# ---------------------------------------------------------------------------


def _existing_open_alert(rule: AIAlertRule, dedup: str) -> AIAlert | None:
    """Open (unresolved/unsuppressed) alert for this rule+scope, if any."""
    return (
        AIAlert.objects.filter(
            dedup_key=dedup, status__in=[AIAlert.Status.TRIGGERED, AIAlert.Status.ACKNOWLEDGED]
        )
        .order_by("-triggered_at")
        .first()
    )


def _recent_alert_within_cooldown(rule: AIAlertRule, dedup: str) -> bool:
    """True if any alert for this scope was created inside the cooldown window."""
    window_start = timezone.now() - timezone.timedelta(minutes=int(rule.cooldown_minutes or 0))
    return AIAlert.objects.filter(dedup_key=dedup, triggered_at__gte=window_start).exists()


def _build_alert_message(rule: AIAlertRule, value: float) -> str:
    scope = _scope_key(rule)
    if scope == "::":
        scope_text = "all features"
    else:
        parts = []
        if rule.feature_id:
            parts.append(f"feature={rule.feature_id}")
        if rule.provider:
            parts.append(f"provider={rule.provider}")
        if rule.model_name:
            parts.append(f"model={rule.model_name}")
        scope_text = ", ".join(parts) or "all features"
    return (
        f"{rule.name} (rule {rule.rule_key}) tripped: {rule.get_metric_display()}= {value}"
        f" {rule.get_operator_display()} {rule.threshold_value} for {scope_text} "
        f"over the last {rule.duration_minutes} min."
    )


def _notify_admins(alert: AIAlert) -> int:
    """Send in-app notifications to active staff/admins. Returns recipient count.

    Mirrors the admin RBAC used by the dashboard views: staff OR role == admin.
    """
    recipients = (
        User.objects.filter(is_active=True)
        .filter(Q(is_staff=True) | Q(role="admin"))
        .order_by("id")
    )
    action_url = f"/dashboard?tab=ai&view=alerts&alert={alert.alert_key}"
    sent = 0
    for user in recipients:
        try:
            create_notification(
                user=user,
                notification_type="ai_alert",
                title=f"[{alert.severity.upper()}] {alert.title}",
                message=alert.message,
                action_url=action_url,
                meta={"alert_key": str(alert.alert_key), "severity": alert.severity},
            )
            sent += 1
        except Exception:
            logger.exception("Failed to notify admin %s about AI alert", user.pk)
    return sent


def evaluate_rule(rule: AIAlertRule, *, actor=None, request=None) -> dict[str, Any]:
    """Evaluate one rule: compute metric, track breach streak, maybe trigger.

    ``actor``/``request`` are only used for audit logging when a caller runs
    evaluation manually through the admin API (defaults None = Celery/system).
    """
    if not rule.is_enabled:
        return {"rule_key": rule.rule_key, "status": "disabled"}

    value = compute_metric_value(rule)
    rule.last_metric_value = value
    rule.last_checked_at = timezone.now()

    if value is None:
        # No data in scope — never accumulates a breach streak.
        rule.breach_count = 0
        rule.save(
            update_fields=["breach_count", "last_metric_value", "last_checked_at", "updated_at"]
        )
        return {"rule_key": rule.rule_key, "status": "no_data", "value": None}

    breached = _is_breach(rule, value)
    rule.breach_count = (rule.breach_count + 1) if breached else 0
    rule.save(update_fields=["breach_count", "last_metric_value", "last_checked_at", "updated_at"])

    if not breached or rule.breach_count < rule.consecutive_checks:
        return {
            "rule_key": rule.rule_key,
            "status": "breached" if breached else "ok",
            "value": value,
            "breach_count": rule.breach_count,
            "triggered": False,
        }

    dedup = _dedup_key(rule)
    open_alert = _existing_open_alert(rule, dedup)
    if open_alert:
        # Fold the continued breach into the open alert (dedup, no noise).
        open_alert.breach_count = rule.breach_count
        open_alert.metric_value = value
        open_alert.save(update_fields=["breach_count", "metric_value", "updated_at"])
        return {
            "rule_key": rule.rule_key,
            "status": "deduplicated",
            "value": value,
            "breach_count": rule.breach_count,
            "triggered": False,
            "alert_id": open_alert.pk,
        }

    if _recent_alert_within_cooldown(rule, dedup):
        return {
            "rule_key": rule.rule_key,
            "status": "cooldown",
            "value": value,
            "breach_count": rule.breach_count,
            "triggered": False,
        }

    alert = AIAlert.objects.create(
        rule=rule,
        alert_type=rule.alert_type,
        severity=rule.severity,
        status=AIAlert.Status.TRIGGERED,
        title=f"{rule.name} — {rule.get_metric_display()} breach",
        message=_build_alert_message(rule, value),
        metric_name=rule.metric,
        metric_value=value,
        threshold_value=rule.threshold_value,
        feature=rule.feature,
        provider=rule.provider,
        model_name=rule.model_name,
        dedup_key=dedup,
        breach_count=rule.breach_count,
        meta={"rule_key": rule.rule_key, "operator": rule.operator},
    )
    notified = _notify_admins(alert) if rule.notify_admins else 0
    log_action(
        actor=actor,
        action="ai_intelligence.alert_triggered",
        target=alert,
        request=request,
        detail={
            "rule_key": rule.rule_key,
            "metric": rule.metric,
            "value": value,
            "threshold": rule.threshold_value,
            "severity": rule.severity,
            "notified_admins": notified,
        },
    )
    return {
        "rule_key": rule.rule_key,
        "status": "triggered",
        "value": value,
        "breach_count": rule.breach_count,
        "triggered": True,
        "alert_id": alert.pk,
        "notified_admins": notified,
    }


def evaluate_all_rules(*, actor=None, request=None) -> dict[str, Any]:
    """Evaluate every enabled rule. Returns a per-rule summary + counts."""
    results = []
    for rule in AIAlertRule.objects.filter(is_enabled=True):
        try:
            results.append(evaluate_rule(rule, actor=actor, request=request))
        except Exception:
            logger.exception("Alert rule evaluation failed for rule=%s", rule.rule_key)
            results.append({"rule_key": rule.rule_key, "status": "error"})
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"evaluated": len(results), "results": results, "counts": counts}


# ---------------------------------------------------------------------------
# Lifecycle actions (admin-authenticated; the views enforce RBAC + audit)
# ---------------------------------------------------------------------------


def acknowledge_alert(alert_id: int, user, note: str = "", request=None) -> AIAlert | None:
    alert = AIAlert.objects.filter(pk=alert_id).first()
    if not alert:
        return None
    if alert.status not in (AIAlert.Status.TRIGGERED, AIAlert.Status.ACKNOWLEDGED):
        raise ValueError(f"Alert is {alert.status}, cannot acknowledge")
    alert.status = AIAlert.Status.ACKNOWLEDGED
    alert.acknowledged_by = user
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "updated_at"])
    log_action(
        actor=user,
        action="ai_intelligence.alert_acknowledged",
        target=alert,
        request=request,
        detail={"note": note[:300]},
    )
    return alert


def resolve_alert(alert_id: int, user, note: str = "", request=None) -> AIAlert | None:
    alert = AIAlert.objects.filter(pk=alert_id).first()
    if not alert:
        return None
    if alert.status == AIAlert.Status.RESOLVED:
        raise ValueError("Alert already resolved")
    alert.status = AIAlert.Status.RESOLVED
    alert.resolved_by = user
    alert.resolved_at = timezone.now()
    alert.resolution_note = note
    alert.save(
        update_fields=[
            "status",
            "resolved_by",
            "resolved_at",
            "resolution_note",
            "updated_at",
        ]
    )
    log_action(
        actor=user,
        action="ai_intelligence.alert_resolved",
        target=alert,
        request=request,
        detail={"note": note[:300]},
    )
    return alert


def suppress_alert(alert_id: int, user, note: str = "", request=None) -> AIAlert | None:
    alert = AIAlert.objects.filter(pk=alert_id).first()
    if not alert:
        return None
    if alert.status == AIAlert.Status.RESOLVED:
        raise ValueError("Resolved alerts cannot be suppressed")
    alert.status = AIAlert.Status.SUPPRESSED
    alert.resolved_by = user
    alert.resolved_at = timezone.now()
    alert.resolution_note = note
    alert.save(
        update_fields=[
            "status",
            "resolved_by",
            "resolved_at",
            "resolution_note",
            "updated_at",
        ]
    )
    log_action(
        actor=user,
        action="ai_intelligence.alert_suppressed",
        target=alert,
        request=request,
        detail={"note": note[:300]},
    )
    return alert
