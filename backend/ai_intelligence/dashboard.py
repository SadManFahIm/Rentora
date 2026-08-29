"""AI Intelligence Dashboard (Phase 18.4) — read-side aggregation queries.

All functions aggregate the *existing* Phase 18.1 telemetry
(``AIExecutionLog``, ``ProviderHealth``), Phase 18.2 registries
(``AIFeatureRegistry``, ``AIPrompt``), Phase 18.3 evaluation
(``EvaluationRun``, ``EvaluationCaseResult``), and the Phase 17 drift engine
(``ml_models.DriftMetric``). No new telemetry/evaluation tables are created.

Cost figures always come from ``AIExecutionLog.estimated_cost_usd`` and are
**estimated**, never claimed as actual billing.

Percentiles use the nearest-rank method over the latency column bounded to a
sane sample (newest records first) to keep dashboard queries memory-friendly.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from config.cache_utils import safe_cache_get, safe_cache_set

# Maximum latency samples used for percentile calcs (newest records win).
MAX_PERCENTILE_SAMPLE = 20000
# Cache TTL for dashboard aggregates (seconds). Kept short so an ops view
# never serves stale outliers for long.
_DASHBOARD_CACHE_TTL = int(getattr(settings, "AI_DASHBOARD_CACHE_TTL_SECONDS", 300))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(values: list[int], pct: float) -> int:
    """Nearest-rank percentile of a list of latencies (ms).

    ``pct`` in [0, 100]. Returns 0 for an empty list.
    """
    if not values:
        return 0
    ordered = sorted(values)
    k = max(1, round(pct / 100 * len(ordered)))
    return int(ordered[min(k, len(ordered)) - 1])


def _latency_percentiles(qs: Any) -> dict[str, int]:
    """Compute avg/p50/p95/p99 from a latency queryset, bounded sample."""
    values = list(
        qs.order_by("-created_at").values_list("latency_ms", flat=True)[:MAX_PERCENTILE_SAMPLE]
    )
    avg = int(sum(values) / len(values)) if values else 0
    return {
        "avg_latency_ms": avg,
        "p50_latency_ms": _percentile(values, 50),
        "p95_latency_ms": _percentile(values, 95),
        "p99_latency_ms": _percentile(values, 99),
        "sample_size": len(values),
    }


def _executions_base(
    feature_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
):
    """Base AIExecutionLog queryset for dashboard aggregations."""
    from .models import AIExecutionLog

    qs = AIExecutionLog.objects.all()
    if feature_id:
        qs = qs.filter(feature_key=feature_id)
    if provider:
        qs = qs.filter(provider=provider)
    if model:
        qs = qs.filter(model_name=model)
    if model_version:
        qs = qs.filter(model_version=model_version)
    return qs


def _executions_window(
    days: int,
    feature_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
):
    """Execution logs within the last ``days`` (clamped 1..365)."""
    days = min(max(int(days), 1), 365)
    since = timezone.now() - timedelta(days=days)
    return _executions_base(feature_id, provider, model, model_version).filter(
        created_at__gte=since
    )


def _cache_key(scope: str, days: int, *parts: str) -> str:
    return "ai:dashboard:{}:{}:{}".format(scope, days, ":".join(parts))


def _cached(scope: str, days: int, build, *parts: str) -> dict | list:
    """Run ``build()`` (a zero-arg callable) and cache the result."""
    key = _cache_key(scope, days, *parts)
    cached = safe_cache_get(key)
    if cached is not None:
        return cached
    result = build()
    safe_cache_set(key, result, _DASHBOARD_CACHE_TTL)
    return result


def _daily_trend(qs: Any, days: int) -> list[dict]:
    """Per-day execution volume/error counts for a queryset."""
    labels = {}
    for i in range(days - 1, -1, -1):
        day = (timezone.now() - timedelta(days=i)).date()
        labels[day] = {"date": day.isoformat(), "count": 0, "errors": 0}

    rows = (
        qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            count=Count("id"), errors=Count("id", filter=Q(status__in=["failure", "timeout"]))
        )
        .order_by("day")
    )
    for row in rows:
        day = row["day"]
        if day in labels:
            labels[day]["count"] = row["count"]
            labels[day]["errors"] = row["errors"]
    return list(labels.values())


def _drift_map() -> dict[str, dict[str, Any]]:
    """Latest drift measurement per (model, metric) → status dict.

    Derives healthy / warning / critical / unknown from the existing binary
    ``DriftMetric.threshold_breached`` plus margin-to-threshold (warning when
    within 20% of an active threshold boundary). Reuses Phase 17 engine data
    — no second drift engine is implemented.
    """
    from ml_models.models import DriftMetric

    result: dict[str, dict[str, Any]] = {}
    metrics = DriftMetric.objects.select_related("model_version").order_by("-created_at")[:500]
    for m in metrics:
        key = f"{m.model_version.name}:{m.metric_name}"
        if key in result:
            continue
        status = "healthy"
        if m.threshold_breached:
            status = "critical"
        else:
            # warning tier: within 10% of an active threshold boundary
            if m.threshold_min is not None and m.value is not None:
                span = abs(m.value - m.threshold_min)
                if span <= m.threshold_min * 0.1:
                    status = "warning"
            elif m.threshold_max is not None and m.value is not None:
                span = abs(m.threshold_max - m.value)
                if span <= m.threshold_max * 0.1:
                    status = "warning"
        result[key] = {
            "model_name": m.model_version.name,
            "model_version": m.model_version.version,
            "metric_name": m.metric_name,
            "value": m.value,
            "baseline_value": m.baseline_value,
            "threshold_min": m.threshold_min,
            "threshold_max": m.threshold_max,
            "threshold_breached": m.threshold_breached,
            "status": status,
            "window_end": m.window_end.isoformat(),
            "last_checked": m.created_at.isoformat(),
        }
    return result


def get_drift_status(model_name: str | None = None) -> list[dict]:
    """Latest drift status for every tracked (model, metric).

    Optional ``model_name`` filter. Statuses: healthy / warning / critical /
    unknown (a tracked model with no measurements is ``unknown``).
    """
    from ml_models.models import ModelVersion

    drift = _drift_map()
    if model_name:
        drift = {k: v for k, v in drift.items() if v["model_name"] == model_name}

    # Models with no measurements → unknown
    versions = ModelVersion.objects.filter(status=ModelVersion.Status.ACTIVE)
    for mv in versions:
        prefix = f"{mv.name}:"
        if not any(k.startswith(prefix) for k in drift):
            drift[f"{mv.name}:no_data"] = {
                "model_name": mv.name,
                "model_version": mv.version,
                "metric_name": "no_data",
                "value": None,
                "baseline_value": None,
                "threshold_min": None,
                "threshold_max": None,
                "threshold_breached": False,
                "status": "unknown",
                "window_end": None,
                "last_checked": None,
            }
    return sorted(drift.values(), key=lambda d: (d["model_name"], d["metric_name"]))


def _open_alerts_count() -> int:
    from .models import AIAlert

    return AIAlert.objects.filter(status__in=["triggered", "acknowledged"]).count()


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def get_ai_summary(
    days: int = 30,
    feature_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Overview KPIs for the AI Intelligence Dashboard.

    Returns real aggregated values from AIExecutionLog — never fabricated.
    """
    days = int(days)

    def build():
        from .models import AIFeatureRegistry

        qs = _executions_window(days, feature_id, provider, model)
        total = qs.count()
        success = qs.filter(status="success").count()
        failed = qs.filter(status__in=["failure", "timeout"]).count()
        fallbacks = qs.filter(is_fallback=True).count()
        success_rate = round((success / total) * 100, 2) if total else 0.0
        fallback_rate = round((fallbacks / total) * 100, 2) if total else 0.0
        error_rate = round((failed / total) * 100, 2) if total else 0.0
        lat = _latency_percentiles(qs)
        cost = qs.aggregate(
            total_cost=Sum("estimated_cost_usd"),
            total_tokens=Sum("total_tokens"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
        )

        # Active model variants seen in telemetry + registry defaults.
        seen_models = set(
            qs.exclude(model_name="")
            .values_list("provider", "model_name", "model_version")
            .distinct()
        )
        active_features = AIFeatureRegistry.objects.filter(is_enabled=True)
        active_model_count = len(seen_models) + len(
            set(
                active_features.exclude(default_model="")
                .values_list("default_provider", "default_model")
                .distinct()
            )
        )

        drift = get_drift_status()
        drift_status = "healthy"
        if any(d["status"] == "critical" for d in drift):
            drift_status = "critical"
        elif any(d["status"] == "warning" for d in drift):
            drift_status = "warning"
        elif not drift:
            drift_status = "unknown"

        summary = {
            "days": days,
            "total_executions": total,
            "successful_executions": success,
            "failed_executions": failed,
            "timeout_executions": qs.filter(status="timeout").count(),
            "rate_limited_executions": qs.filter(status="rate_limited").count(),
            "success_rate": success_rate,
            "error_rate": error_rate,
            "avg_latency_ms": lat["avg_latency_ms"],
            "p50_latency_ms": lat["p50_latency_ms"],
            "p95_latency_ms": lat["p95_latency_ms"],
            "p99_latency_ms": lat["p99_latency_ms"],
            "latency_sample_size": lat["sample_size"],
            "fallback_rate": fallback_rate,
            "estimated_cost_usd": round(float(cost["total_cost"] or 0), 6),
            "total_tokens": int(cost["total_tokens"] or 0),
            "input_tokens": int(cost["input_tokens"] or 0),
            "output_tokens": int(cost["output_tokens"] or 0),
            "cost_source": "estimated",
            "active_features": active_features.count(),
            "active_models": active_model_count,
            "open_alerts": _open_alerts_count(),
            "drift_status": drift_status,
            "trend": _daily_trend(qs, days),
            "is_estimated_cost": True,
        }
        return summary

    return _cached("summary", days, build, feature_id or "-", provider or "-", model or "-")


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


def _feature_aggregates(days: int, feature_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Per-feature aggregate map from execution logs (avoids N+1)."""
    from .models import AIExecutionLog

    since = timezone.now() - timedelta(days=int(days))
    qs = AIExecutionLog.objects.filter(created_at__gte=since)
    if feature_id:
        qs = qs.filter(feature_key=feature_id)

    rows = (
        qs.values("feature_key")
        .annotate(
            total=Count("id"),
            success=Count("id", filter=Q(status="success")),
            failed=Count("id", filter=Q(status__in=["failure", "timeout"])),
            timeouts=Count("id", filter=Q(status="timeout")),
            fallbacks=Count("id", filter=Q(is_fallback=True)),
            provider_failures=Count("id", filter=Q(failure_type="provider_failure")),
            avg_latency=Avg("latency_ms"),
            total_cost=Sum("estimated_cost_usd"),
            total_tokens=Sum("total_tokens"),
        )
        .order_by("feature_key")
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        total = r["total"] or 0
        out[r["feature_key"]] = {
            "feature_key": r["feature_key"],
            "total_executions": total,
            "successful_executions": r["success"] or 0,
            "failed_executions": r["failed"] or 0,
            "timeout_executions": r["timeouts"] or 0,
            "success_rate": round((r["success"] / total) * 100, 2) if total else 0.0,
            "error_rate": round((r["failed"] / total) * 100, 2) if total else 0.0,
            "timeout_rate": round((r["timeouts"] / total) * 100, 2) if total else 0.0,
            "fallback_rate": round((r["fallbacks"] / total) * 100, 2) if total else 0.0,
            "avg_latency_ms": int(r["avg_latency"] or 0),
            "estimated_cost_usd": round(float(r["total_cost"] or 0), 6),
            "total_tokens": int(r["total_tokens"] or 0),
            "provider_failures": r["provider_failures"] or 0,
        }
    return out


def _enrich_feature(row: dict[str, Any], feature, lat: dict[str, Any]) -> dict[str, Any]:
    """Blend registry + evaluation + drift context into a feature row."""
    from .models import EvaluationRun

    latest_run = (
        EvaluationRun.objects.filter(feature=feature, status="completed")
        .order_by("-created_at")
        .select_related("dataset")
        .first()
    )
    active_prompt = feature.prompts.filter(status="active").first()

    enriched = dict(row)
    enriched.update(
        {
            "feature_id": feature.feature_id,
            "name": feature.name,
            "category": feature.category,
            "status": feature.status,
            "is_enabled": feature.is_enabled,
            "available": feature.is_enabled,
            "active_provider": feature.default_provider,
            "active_model": feature.default_model,
            "feature_flag_key": feature.feature_flag_key,
            "active_prompt": active_prompt.prompt_key if active_prompt else "",
            "active_prompt_version": (
                getattr(active_prompt, "active_version", None)
                and active_prompt.active_version.version
            )
            or 0,
            "latest_evaluation_score": (round(latest_run.score, 4) if latest_run else None),
            "latest_evaluation_metric_scores": latest_run.metric_scores if latest_run else {},
            "latest_evaluation_date": (
                latest_run.completed_at.isoformat()
                if latest_run and latest_run.completed_at
                else None
            ),
            "latest_evaluation_status": latest_run.status if latest_run else "none",
            "last_execution": row.get("last_execution"),
            "p50_latency_ms": lat["p50_latency_ms"] if row["total_executions"] else 0,
            "p95_latency_ms": lat["p95_latency_ms"] if row["total_executions"] else 0,
            "p99_latency_ms": lat["p99_latency_ms"] if row["total_executions"] else 0,
        }
    )
    return enriched


def get_feature_health_list(days: int = 30) -> list[dict[str, Any]]:
    """Health summary for every registered AI feature."""
    from .models import AIExecutionLog, AIFeatureRegistry

    days = int(days)

    def build():
        aggregates = _feature_aggregates(days)
        # latency percentiles per feature (bounded)
        since = timezone.now() - timedelta(days=days)
        latencies: dict[str, dict[str, int]] = {}
        qs = AIExecutionLog.objects.filter(created_at__gte=since)
        for fk_id in list(aggregates.keys())[:200]:
            latencies[fk_id] = _latency_percentiles(qs.filter(feature_key=fk_id))
        # last execution timestamp per feature
        last_exec = {
            r["feature_key"]: r["last"]
            for r in (
                AIExecutionLog.objects.filter(created_at__gte=since)
                .values("feature_key")
                .annotate(last=Max("created_at"))
            )
        }

        rows = []
        for feature in AIFeatureRegistry.objects.prefetch_related("prompts").all():
            row = aggregates.get(
                feature.feature_id,
                {
                    "feature_key": feature.feature_id,
                    "total_executions": 0,
                    "successful_executions": 0,
                    "failed_executions": 0,
                    "timeout_executions": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "timeout_rate": 0.0,
                    "fallback_rate": 0.0,
                    "avg_latency_ms": 0,
                    "estimated_cost_usd": 0.0,
                    "total_tokens": 0,
                    "provider_failures": 0,
                },
            )
            row["last_execution"] = (
                last_exec[feature.feature_id].isoformat()
                if last_exec.get(feature.feature_id)
                else None
            )
            lat = latencies.get(feature.feature_id, {})
            rows.append(_enrich_feature(row, feature, lat))
        rows.sort(key=lambda r: r["feature_id"])
        return rows

    return _cached("features", days, build)


def get_feature_health_detail(feature_id: str, days: int = 30) -> dict[str, Any]:
    """Drill-down for a single AI feature: usage/performance/reliability/
    cost/quality/configuration/drift."""
    from .models import AIFeatureRegistry

    days = int(days)

    def build():
        feature = (
            AIFeatureRegistry.objects.prefetch_related("prompts")
            .filter(feature_id=feature_id)
            .first()
        )
        if not feature:
            return {"error": f"Unknown feature: {feature_id}"}

        window_qs = _executions_window(days, feature_id=feature_id)
        total = window_qs.count()
        success = window_qs.filter(status="success").count()
        fallbacks = window_qs.filter(is_fallback=True).count()
        failed = window_qs.filter(status__in=["failure", "timeout"]).count()
        timeouts = window_qs.filter(status="timeout").count()
        provider_failures = window_qs.filter(failure_type="provider_failure").count()
        cost_agg = window_qs.aggregate(
            total_cost=Sum("estimated_cost_usd"), total_tokens=Sum("total_tokens")
        )

        # Provider / model breakdowns
        by_provider = list(
            window_qs.values("provider")
            .annotate(count=Count("id"), cost=Sum("estimated_cost_usd"))
            .order_by("-count")
        )
        by_model = list(
            window_qs.values("provider", "model_name", "model_version")
            .annotate(count=Count("id"), cost=Sum("estimated_cost_usd"))
            .order_by("-count")
        )

        lat = _latency_percentiles(window_qs)

        # Usage trend
        trend = _daily_trend(window_qs, days)

        # Distinct users/tenants in telemetry
        user_count = window_qs.exclude(user=None).values("user").distinct().count()

        # Quality: latest completed evaluation run + regression check
        from .models import EvaluationRun
        from .services import check_regression

        latest_run = (
            EvaluationRun.objects.filter(feature=feature, status="completed")
            .order_by("-created_at")
            .select_related("dataset", "prompt")
            .prefetch_related("case_results")
            .first()
        )
        quality = {
            "latest_evaluation_score": round(latest_run.score, 4) if latest_run else None,
            "baseline_score": None,
            "score_delta": None,
            "regression_status": "none",
            "regression_count": 0,
            "regressions": [],
            "latest_evaluation_date": (
                latest_run.completed_at.isoformat()
                if latest_run and latest_run.completed_at
                else None
            ),
            "latest_run_metric_scores": latest_run.metric_scores if latest_run else {},
            "pass_rate": latest_run.pass_rate if latest_run else None,
            "dataset_key": latest_run.dataset.dataset_key
            if latest_run and latest_run.dataset
            else None,
        }
        if latest_run:
            reg = check_regression(latest_run.pk)
            quality["regression_status"] = "regression" if reg.get("has_regression") else "ok"
            quality["regression_count"] = reg.get("regression_count", 0)
            quality["regressions"] = reg.get("regressions", [])[:5]
            first = (reg.get("regressions") or [{}])[0]
            if first.get("baseline") is not None and first.get("current") is not None:
                quality["baseline_score"] = first["baseline"]
                quality["score_delta"] = round(first["current"] - first["baseline"], 4)

        # Configuration
        active_prompt = feature.prompts.filter(status="active").first()
        config = {
            "active_provider": feature.default_provider,
            "active_model": feature.default_model,
            "active_prompt": active_prompt.prompt_key if active_prompt else "",
            "active_prompt_version": (
                getattr(active_prompt, "active_version", None)
                and active_prompt.active_version.version
            )
            or 0,
            "feature_flag_key": feature.feature_flag_key,
            "fallback_strategy": feature.fallback_strategy,
            "status": feature.status,
            "is_enabled": feature.is_enabled,
        }

        # Drift — platform-level drift (features do not own drift metrics).
        platform_drift = [d for d in get_drift_status()]

        return {
            "feature_id": feature.feature_id,
            "name": feature.name,
            "category": feature.category,
            "usage": {
                "total_executions": total,
                "successful_executions": success,
                "failed_executions": failed,
                "success_rate": round((success / total) * 100, 2) if total else 0.0,
                "distinct_users": user_count,
                "trend": trend,
            },
            "performance": lat,
            "reliability": {
                "error_rate": round((failed / total) * 100, 2) if total else 0.0,
                "timeout_rate": round((timeouts / total) * 100, 2) if total else 0.0,
                "fallback_rate": round((fallbacks / total) * 100, 2) if total else 0.0,
                "provider_failures": provider_failures,
            },
            "cost": {
                "estimated_total_cost_usd": round(float(cost_agg["total_cost"] or 0), 6),
                "cost_per_execution_usd": round(float(cost_agg["total_cost"] or 0) / total, 8)
                if total
                else 0.0,
                "total_tokens": int(cost_agg["total_tokens"] or 0),
                "by_provider": [
                    {
                        "provider": b["provider"],
                        "count": b["count"],
                        "cost_usd": round(float(b["cost"] or 0), 6),
                    }
                    for b in by_provider
                ],
                "by_model": [
                    {
                        "provider": b["provider"],
                        "model_name": b["model_name"],
                        "model_version": b["model_version"],
                        "count": b["count"],
                        "cost_usd": round(float(b["cost"] or 0), 6),
                    }
                    for b in by_model
                ],
                "is_estimated_cost": True,
            },
            "quality": quality,
            "configuration": config,
            "drift": platform_drift,
        }

    return _cached("feature-detail", days, build, feature_id)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def get_model_health(days: int = 30) -> dict[str, Any]:
    """Model health view: telemetry + evaluation per (provider, model)."""
    from .models import EvaluationRun

    days = int(days)

    def build():
        since = timezone.now() - timedelta(days=days)
        rows = list(
            _executions_base()
            .filter(created_at__gte=since)
            .exclude(model_name="")
            .values("provider", "model_name", "model_version")
            .annotate(
                total=Count("id"),
                success=Count("id", filter=Q(status="success")),
                failed=Count("id", filter=Q(status__in=["failure", "timeout"])),
                fallbacks=Count("id", filter=Q(is_fallback=True)),
                timeouts=Count("id", filter=Q(status="timeout")),
                avg_latency=Avg("latency_ms"),
                total_cost=Sum("estimated_cost_usd"),
            )
            .order_by("-total")
        )

        # latest evaluation run per model_name (bounded iteration — pass_rate
        # is a computed property, not a DB column, so we read instances).
        eval_rows: dict[str, dict[str, Any]] = {}
        for run in (
            EvaluationRun.objects.filter(status="completed")
            .exclude(model_name="")
            .order_by("model_name", "-created_at")[:5000]
        ):
            if run.model_name not in eval_rows:
                eval_rows[run.model_name] = {
                    "score": run.score,
                    "pass_rate": run.pass_rate,
                    "completed_at": run.completed_at,
                }
            if len(eval_rows) >= 300:
                break

        models = []
        for r in rows:
            total = r["total"] or 0
            name = r["model_name"] or "(unnamed)"
            ev = eval_rows.get(r["model_name"])
            models.append(
                {
                    "provider": r["provider"],
                    "model_name": name,
                    "model_version": r["model_version"],
                    "total_executions": total,
                    "success_rate": round((r["success"] / total) * 100, 2) if total else 0.0,
                    "error_rate": round((r["failed"] / total) * 100, 2) if total else 0.0,
                    "timeout_rate": round((r["timeouts"] / total) * 100, 2) if total else 0.0,
                    "fallback_rate": round((r["fallbacks"] / total) * 100, 2) if total else 0.0,
                    "avg_latency_ms": int(r["avg_latency"] or 0),
                    "estimated_cost_usd": round(float(r["total_cost"] or 0), 6),
                    "latest_evaluation_score": (round(ev["score"], 4) if ev else None),
                    "latest_evaluation_pass_rate": ev["pass_rate"] if ev else None,
                    "latest_evaluation_date": (
                        ev["completed_at"].isoformat() if ev and ev["completed_at"] else None
                    ),
                }
            )
        models.sort(key=lambda m: (m["provider"], m["model_name"], m["model_version"]))
        return models

    return _cached("models", days, build)


def compare_model_versions(
    provider: str, model: str, version_a: str, version_b: str, days: int = 90
) -> dict[str, Any]:
    """Compare the latest completed evaluation for two model variants.

    ``EvaluationRun`` has no ``model_version`` column, so a "variant" matches
    either the run's ``model_name`` or its ``metadata["model_version"]``.
    Read-only comparison — never switches production models.
    """
    from django.db.models import Q

    from .models import EvaluationRun

    def latest_for(version: str):
        return (
            EvaluationRun.objects.filter(
                provider=provider,
                status="completed",
            )
            .filter(Q(model_name=version) | Q(metadata__model_version=version))
            .order_by("-created_at")
            .select_related("dataset")
            .first()
        )

    def build():
        run_a = latest_for(version_a)
        run_b = latest_for(version_b)
        if not run_a and not run_b:
            return {"error": "No completed evaluation runs for either version."}

        def snapshot(run):
            if not run:
                return None
            aggregate = run.case_results.aggregate(
                avg_latency=Avg("latency_ms"),
                passed=Count("id", filter=Q(passed=True)),
                total=Count("id"),
            )
            return {
                "run_id": run.pk,
                "run_key": str(run.run_key),
                "score": run.score,
                "pass_rate": run.pass_rate,
                "metric_scores": run.metric_scores,
                "avg_latency_ms": int(aggregate["avg_latency"] or 0),
                "total_cost_usd": float(run.total_cost_usd),
                "dataset_key": run.dataset.dataset_key if run.dataset else None,
                "completed_at": (run.completed_at.isoformat() if run.completed_at else None),
            }

        a = snapshot(run_a)
        b = snapshot(run_b)
        deltas = {}
        if a and b:
            deltas = {
                "score_delta": round(b["score"] - a["score"], 4),
                "pass_rate_delta": round(b["pass_rate"] - a["pass_rate"], 4),
                "latency_delta_ms": b["avg_latency_ms"] - a["avg_latency_ms"],
                "cost_delta_usd": round(b["total_cost_usd"] - a["total_cost_usd"], 6),
            }
        return {
            "provider": provider,
            "model_name": model,
            "version_a": a,
            "version_b": b,
            "deltas": deltas,
            "winner": (
                "b"
                if a and b and b["score"] > a["score"]
                else ("a" if a and b and a["score"] > b["score"] else "tie")
            ),
            "production_switch_automated": False,
        }

    return _cached("model-compare", days, build, provider, model, version_a, version_b)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def get_provider_health(days: int = 30) -> dict[str, Any]:
    """Provider-level operational health from telemetry + health windows."""
    from .models import ProviderHealth

    days = int(days)

    def build():
        since = timezone.now() - timedelta(days=days)
        rows = list(
            _executions_base()
            .filter(created_at__gte=since)
            .values("provider")
            .annotate(
                total=Count("id"),
                success=Count("id", filter=Q(status="success")),
                failed=Count("id", filter=Q(status__in=["failure", "timeout"])),
                fallbacks=Count("id", filter=Q(is_fallback=True)),
                avg_latency=Avg("latency_ms"),
                total_cost=Sum("estimated_cost_usd"),
            )
            .order_by("-total")
        )
        lat_map = {}
        base = _executions_base().filter(created_at__gte=since)
        for provider in [r["provider"] for r in rows]:
            lat_map[provider] = _latency_percentiles(base.filter(provider=provider))

        # Latest health window per provider (from the hourly aggregation)
        latest_health = {}
        for ph in ProviderHealth.objects.order_by("-window_start").values(
            "provider", "window_start", "success_rate", "is_healthy"
        ):
            if ph["provider"] not in latest_health:
                latest_health[ph["provider"]] = {
                    "window_start": ph["window_start"].isoformat(),
                    "success_rate": ph["success_rate"],
                    "is_healthy": ph["is_healthy"],
                }

        providers = []
        for r in rows:
            total = r["total"] or 0
            lat = lat_map.get(r["provider"], {})
            health = latest_health.get(r["provider"], {})
            providers.append(
                {
                    "provider": r["provider"],
                    "total_requests": total,
                    "success_rate": round((r["success"] / total) * 100, 2) if total else 0.0,
                    "error_rate": round((r["failed"] / total) * 100, 2) if total else 0.0,
                    "fallback_rate": round((r["fallbacks"] / total) * 100, 2) if total else 0.0,
                    "avg_latency_ms": lat.get("avg_latency_ms", int(r["avg_latency"] or 0)),
                    "p95_latency_ms": lat.get("p95_latency_ms", 0),
                    "estimated_cost_usd": round(float(r["total_cost"] or 0), 6),
                    "latest_health_window": health.get("window_start"),
                    "health_window_success_rate": health.get("success_rate"),
                    "is_healthy": health.get("is_healthy", True),
                    "availability_status": "healthy"
                    if health.get("is_healthy", True)
                    else "degraded",
                }
            )
        providers.sort(key=lambda p: p["provider"])
        return providers

    return _cached("providers", days, build)


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


def get_cost_dashboard(days: int = 30) -> dict[str, Any]:
    """AI cost intelligence (ESTIMATED USD from telemetry)."""

    days = int(days)

    def build():
        since = timezone.now() - timedelta(days=days)
        qs = _executions_base().filter(created_at__gte=since)
        agg = qs.aggregate(
            total_cost=Sum("estimated_cost_usd"),
            total_tokens=Sum("total_tokens"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            total=Count("id"),
            success=Count("id", filter=Q(status="success")),
        )
        total_cost = float(agg["total_cost"] or 0)
        total = agg["total"] or 0
        success = agg["success"] or 0
        # is_fallback rate for spend context handled elsewhere.

        # Daily trend
        daily = _daily_cost_trend(qs, days)
        # Previous equal window for anomaly comparison
        prev_since = since - timedelta(days=days)
        prev_cost = float(
            _executions_base()
            .filter(created_at__gte=prev_since, created_at__lt=since)
            .aggregate(c=Sum("estimated_cost_usd"))["c"]
            or 0
        )
        pct_change = round(((total_cost - prev_cost) / prev_cost) * 100, 2) if prev_cost else None

        by_feature = list(
            qs.values("feature_key")
            .annotate(cost=Sum("estimated_cost_usd"), count=Count("id"))
            .order_by("-cost")
        )
        by_provider = list(
            qs.values("provider")
            .annotate(cost=Sum("estimated_cost_usd"), count=Count("id"))
            .order_by("-cost")
        )
        by_model = list(
            qs.filter(model_name__isnull=False)
            .exclude(model_name="")
            .values("provider", "model_name")
            .annotate(cost=Sum("estimated_cost_usd"), count=Count("id"))
            .order_by("-cost")
        )

        top_feature = by_feature[0] if by_feature else None
        anomalies = []
        if pct_change is not None and pct_change >= 20:
            anomalies.append(
                {
                    "type": "cost_increase",
                    "message": (
                        f"Estimated cost increased {pct_change}% vs the previous {days}-day window."
                    ),
                    "severity": "warning",
                }
            )
        if top_feature and total_cost and (float(top_feature["cost"] or 0) / total_cost) > 0.6:
            name = top_feature["feature_key"]
            share = round((float(top_feature["cost"] or 0) / total_cost) * 100, 1)
            anomalies.append(
                {
                    "type": "cost_concentration",
                    "message": f"{name} holds {share}% of estimated AI spend.",
                    "severity": "info",
                }
            )

        return {
            "days": days,
            "is_estimated_cost": True,
            "currency": "USD",
            "total_estimated_cost_usd": round(total_cost, 6),
            "cost_per_execution_usd": round(total_cost / total, 8) if total else 0.0,
            "cost_per_successful_execution_usd": (
                round(total_cost / success, 8) if success else 0.0
            ),
            "total_tokens": int(agg["total_tokens"] or 0),
            "input_tokens": int(agg["input_tokens"] or 0),
            "output_tokens": int(agg["output_tokens"] or 0),
            "trend": daily,
            "vs_previous_window_pct": pct_change,
            "by_feature": [
                {
                    "feature_key": b["feature_key"],
                    "cost_usd": round(float(b["cost"] or 0), 6),
                    "count": b["count"],
                }
                for b in by_feature
            ],
            "by_provider": [
                {
                    "provider": b["provider"],
                    "cost_usd": round(float(b["cost"] or 0), 6),
                    "count": b["count"],
                }
                for b in by_provider
            ],
            "by_model": [
                {
                    "provider": b["provider"],
                    "model_name": b["model_name"],
                    "cost_usd": round(float(b["cost"] or 0), 6),
                    "count": b["count"],
                }
                for b in by_model
            ],
            "anomalies": anomalies,
        }

    return _cached("cost", days, build)


def _daily_cost_trend(qs: Any, days: int) -> list[dict]:
    labels = {}
    for i in range(days - 1, -1, -1):
        day = (timezone.now() - timedelta(days=i)).date()
        labels[day] = {"date": day.isoformat(), "cost_usd": 0.0, "count": 0}
    rows = (
        qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(cost=Sum("estimated_cost_usd"), count=Count("id"))
        .order_by("day")
    )
    for row in rows:
        if row["day"] in labels:
            labels[row["day"]]["cost_usd"] = round(float(row["cost"] or 0), 6)
            labels[row["day"]]["count"] = row["count"]
    return list(labels.values())


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def get_performance_dashboard(days: int = 30) -> dict[str, Any]:
    """Latency dashboard: overall, per feature/model/provider, daily trend."""
    days = int(days)

    def build():
        since = timezone.now() - timedelta(days=days)
        base = _executions_base().filter(created_at__gte=since)
        overall = _latency_percentiles(base)

        # daily avg trend
        rows = (
            base.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(avg=Avg("latency_ms"), count=Count("id"))
            .order_by("day")
        )
        labels = {}
        for i in range(days - 1, -1, -1):
            labels[(timezone.now() - timedelta(days=i)).date()] = 0.0
        for row in rows:
            if row["day"] in labels:
                labels[row["day"]] = int(row["avg"] or 0)
        trend = [{"date": d.isoformat(), "avg_latency_ms": v} for d, v in labels.items()]

        def breakdown(field: str, qs: Any) -> list[dict]:
            out = []
            for row in (
                qs.values(field)
                .annotate(avg=Avg("latency_ms"), count=Count("id"))
                .order_by("-count")
            ):
                if not row[field]:
                    continue
                out.append(
                    {
                        field: row[field],
                        "avg_latency_ms": int(row["avg"] or 0),
                        "count": row["count"],
                        "p95_latency_ms": _latency_percentiles(qs.filter(**{field: row[field]}))[
                            "p95_latency_ms"
                        ],
                    }
                )
            return out

        # Detect abnormal latency increase vs previous equal window
        prev_since = since - timedelta(days=days)
        prev_avg = (
            _executions_base()
            .filter(created_at__gte=prev_since, created_at__lt=since)
            .aggregate(a=Avg("latency_ms"))["a"]
        )
        anomaly = None
        if prev_avg and overall["avg_latency_ms"] > prev_avg * 1.2:
            anomaly = {
                "detected": True,
                "current_avg_ms": overall["avg_latency_ms"],
                "previous_avg_ms": int(prev_avg),
                "increase_pct": round((overall["avg_latency_ms"] - prev_avg) / prev_avg * 100, 1),
                "message": (
                    f"Average latency increased {(overall['avg_latency_ms'] - prev_avg) / prev_avg * 100:.1f}% "
                    "vs the previous equal window."
                ),
            }

        return {
            "days": days,
            "overall": overall,
            "daily_trend": trend,
            "by_feature": breakdown("feature_key", base),
            "by_provider": breakdown("provider", base),
            "by_model": breakdown("model_name", base.exclude(model_name="")),
            "abnormal_latency_increase": anomaly,
        }

    return _cached("performance", days, build)


# ---------------------------------------------------------------------------
# Errors & reliability
# ---------------------------------------------------------------------------


def get_error_dashboard(days: int = 30, feature_id: str | None = None) -> dict[str, Any]:
    """Error/reliability dashboard with per-scope breakdowns."""
    days = int(days)

    def build():
        qs = _executions_window(days, feature_id=feature_id)
        total = qs.count()
        failed = qs.filter(status__in=["failure", "timeout"])
        errors = failed.count()
        timeouts = qs.filter(status="timeout").count()
        fallbacks = qs.filter(is_fallback=True).count()

        failure_type_breakdown = list(
            qs.exclude(failure_type="none")
            .values("failure_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        status_breakdown = list(qs.values("status").annotate(count=Count("id")).order_by("-count"))

        by_feature = list(
            failed.values("feature_key").annotate(count=Count("id")).order_by("-count")
        )
        by_provider = list(failed.values("provider").annotate(count=Count("id")).order_by("-count"))
        by_model = list(
            failed.exclude(model_name="")
            .values("model_name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Fallback reasons — from error messages of fallback executions (sanitized).
        fallback_reason_rows = (
            qs.filter(is_fallback=True)
            .exclude(error_message="")
            .values("error_message")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )
        fallback_reasons = [
            {
                "reason": (r["error_message"][:200] if r["error_message"] else "unknown"),
                "count": r["count"],
            }
            for r in fallback_reason_rows
        ]

        return {
            "days": days,
            "total_errors": errors,
            "error_rate": round(errors / total * 100, 2) if total else 0.0,
            "timeout_count": timeouts,
            "timeout_rate": round(timeouts / total * 100, 2) if total else 0.0,
            "fallback_count": fallbacks,
            "fallback_rate": round(fallbacks / total * 100, 2) if total else 0.0,
            "failure_type_breakdown": [
                {"failure_type": r["failure_type"], "count": r["count"]}
                for r in failure_type_breakdown
            ],
            "status_breakdown": [
                {"status": r["status"], "count": r["count"]} for r in status_breakdown
            ],
            "by_feature": [
                {"feature_key": r["feature_key"], "count": r["count"]} for r in by_feature
            ],
            "by_provider": [{"provider": r["provider"], "count": r["count"]} for r in by_provider],
            "by_model": [{"model_name": r["model_name"], "count": r["count"]} for r in by_model],
            "fallback_reasons": fallback_reasons,
        }

    return _cached("errors", days, build, feature_id or "-")


# ---------------------------------------------------------------------------
# Quality / Evaluation
# ---------------------------------------------------------------------------


def get_quality_dashboard(feature_id: str | None = None, days: int = 180) -> dict[str, Any]:
    """Latest evaluation/quality per feature, with metric + evaluator type.

    Uses per-category metrics (NDCG for search, F1 for fraud, MAE/RMSE for
    prediction, etc.) surfaced from each run's ``metric_scores`` — it does NOT
    force every feature into one universal score.
    """
    from .models import EvaluationRun

    days = int(days)

    def build():
        runs_qs = EvaluationRun.objects.filter(status="completed").select_related(
            "feature", "dataset", "prompt"
        )
        run_since = timezone.now() - timedelta(days=days)
        latest_per_feature = {}
        for run in runs_qs.filter(created_at__gte=run_since).order_by("feature_id", "-created_at"):
            if run.feature_id and run.feature.feature_id not in latest_per_feature:
                latest_per_feature[run.feature.feature_id] = run

        rows = []
        for run in latest_per_feature.values():
            rows.append(
                {
                    "feature_id": run.feature.feature_id,
                    "feature_name": run.feature.name,
                    "category": run.feature.category,
                    "run_id": run.pk,
                    "run_key": str(run.run_key),
                    "score": run.score,
                    "pass_rate": run.pass_rate,
                    "metric_scores": run.metric_scores,
                    "dataset_key": run.dataset.dataset_key if run.dataset else None,
                    "provider": run.provider,
                    "model_name": run.model_name,
                    "prompt_key": run.prompt.prompt_key if run.prompt else None,
                    "prompt_version": run.prompt_version,
                    "completed_at": (run.completed_at.isoformat() if run.completed_at else None),
                }
            )
        rows.sort(key=lambda r: r["feature_id"])
        return {
            "days": days,
            # Evaluator taxonomy from the metric registry (type per metric).
            "evaluator_types": {
                "deterministic": "Deterministic (computed against ground truth)",
                "heuristic": "Heuristic (approximate/rule-based)",
                "llm_judge": "LLM-as-judge (model-rated quality)",
                "human": "Human review",
            },
            "features": rows,
            "metrics": _metric_catalog(),
        }

    return _cached("quality", days, build, feature_id or "-")


def _metric_catalog() -> list[dict[str, Any]]:
    from .models import EvaluationMetric

    return [
        {
            "metric_key": m.metric_key,
            "name": m.name,
            "category": m.category,
            "metric_type": m.metric_type,
            "is_higher_better": m.is_higher_better,
        }
        for m in EvaluationMetric.objects.all().order_by("metric_key")
    ]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def get_prompt_health(days: int = 90) -> list[dict[str, Any]]:
    """Prompt health: active/previous version, feature, model, latest eval."""
    from .models import AIPrompt, EvaluationRun

    days = int(days)

    def build():
        prompt_runs: dict[int, dict[str, Any]] = {}
        for run in EvaluationRun.objects.filter(
            status="completed",
            prompt__isnull=False,
            created_at__gte=timezone.now() - timedelta(days=days),
        ).order_by("prompt_id", "-created_at")[:5000]:
            if run.prompt_id not in prompt_runs:
                prompt_runs[run.prompt_id] = {
                    "score": run.score,
                    "pass_rate": run.pass_rate,
                    "metric_scores": run.metric_scores,
                    "completed_at": run.completed_at,
                    "model_name": run.model_name,
                    "provider": run.provider,
                }
            if len(prompt_runs) >= 500:
                break
        rows = []
        for prompt in AIPrompt.objects.select_related("feature").prefetch_related("versions").all():
            versions = list(prompt.versions.order_by("-version"))
            active = next((v for v in versions if v.is_active), None)
            prev = None
            if active:
                idx = next((i for i, v in enumerate(versions) if v.pk == active.pk), None)
                if idx is not None:
                    prev = versions[idx + 1] if idx + 1 < len(versions) else None
            ev = prompt_runs.get(prompt.pk)
            rows.append(
                {
                    "prompt_key": prompt.prompt_key,
                    "name": prompt.name,
                    "status": prompt.status,
                    "active_version": active.version if active else None,
                    "previous_version": prev.version if prev else None,
                    "version_count": len(versions),
                    "feature_id": prompt.feature.feature_id if prompt.feature else None,
                    "default_model": prompt.default_model,
                    "latest_evaluation_score": round(ev["score"], 4) if ev else None,
                    "latest_evaluation_pass_rate": ev["pass_rate"] if ev else None,
                    "latest_evaluation_metric_scores": ev["metric_scores"] if ev else {},
                    "latest_evaluation_model": ev["model_name"] if ev else None,
                    "latest_evaluation_date": (
                        ev["completed_at"].isoformat() if ev and ev["completed_at"] else None
                    ),
                    "last_updated": prompt.updated_at.isoformat(),
                }
            )
        return rows

    return _cached("prompts", days, build)


def invalidate_dashboard_cache() -> None:
    """Best-effort cache wipe (used when a scope changes materially)."""
    try:
        from django.core.cache import cache

        keys = cache.keys("ai:dashboard:*")
        if keys:
            cache.delete_many(keys)
    except Exception:
        pass
