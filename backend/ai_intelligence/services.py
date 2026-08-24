"""AI Intelligence Layer — Phase 18.1 services.

Provides:
- Feature registry management
- Execution log querying and aggregation
- Provider health monitoring
- Cost calculation utilities

All functions are designed to be non-blocking and fail gracefully.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_feature_registry(feature_key: str) -> Any:
    """Get a feature from the registry, or None if not found."""
    from .models import AIFeatureRegistry

    try:
        return AIFeatureRegistry.objects.get(feature_id=feature_key)
    except AIFeatureRegistry.DoesNotExist:
        return None


def register_feature(
    feature_id: str,
    name: str,
    category: str = "other",
    description: str = "",
    default_provider: str = "",
    available_providers: list[str] | None = None,
    settings_key: str = "",
    estimated_cost_per_request: float = 0,
    metadata: dict | None = None,
) -> Any:
    """Register or update an AI feature in the registry.

    Idempotent — creates or updates the feature.
    """
    from .models import AIFeatureRegistry

    feature, created = AIFeatureRegistry.objects.update_or_create(
        feature_id=feature_id,
        defaults={
            "name": name,
            "category": category,
            "description": description,
            "default_provider": default_provider,
            "available_providers": available_providers or [],
            "settings_key": settings_key,
            "estimated_cost_per_request": Decimal(str(estimated_cost_per_request)),
            "metadata": metadata or {},
        },
    )
    action = "Created" if created else "Updated"
    logger.info("%s AI feature: %s", action, feature_id)
    return feature


def log_execution(
    execution_id: Any,
    feature_id: str,
    provider: str,
    status: str = "success",
    latency_ms: int = 0,
    confidence: float = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float = 0,
    user: Any = None,
    request_id: str = "",
    failure_type: str = "none",
    error_message: str = "",
    model_name: str = "",
    model_version: str = "",
    is_fallback: bool = False,
    primary_provider: str = "",
    fallback_chain: list[str] | None = None,
    metadata: dict | None = None,
) -> Any:
    """Log an AI execution to the telemetry store.

    Non-blocking — catches and logs all exceptions.
    """
    from .models import AIExecutionLog

    try:
        with transaction.atomic():
            log = AIExecutionLog.objects.create(
                execution_id=execution_id,
                feature_key=feature_id,
                provider=provider,
                status=status,
                latency_ms=latency_ms,
                confidence=confidence,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                estimated_cost_usd=Decimal(str(estimated_cost_usd)),
                user=user if user and user.is_authenticated else None,
                request_id=request_id,
                failure_type=failure_type,
                error_message=error_message,
                model_name=model_name,
                model_version=model_version,
                is_fallback=is_fallback,
                primary_provider=primary_provider,
                fallback_chain=fallback_chain or [],
                metadata=metadata or {},
            )
            return log
    except Exception:
        logger.debug("Failed to log AI execution", exc_info=True)
        return None


def get_provider_stats(
    feature_id: str | None = None,
    provider: str | None = None,
    hours: int = 24,
) -> dict[str, Any]:
    """Get aggregated provider statistics for a time window.

    Returns dict with:
    - total_requests, successful, failed, success_rate
    - avg_latency_ms, p95_latency_ms
    - total_cost_usd, total_tokens
    - by_provider: per-provider breakdown
    """
    from .models import AIExecutionLog

    since = timezone.now() - timedelta(hours=hours)
    qs = AIExecutionLog.objects.filter(created_at__gte=since)

    if feature_id:
        qs = qs.filter(feature_key=feature_id)
    if provider:
        qs = qs.filter(provider=provider)

    stats = qs.aggregate(
        total_requests=Count("id"),
        successful=Count("id", filter=Q(status="success")),
        failed=Count("id", filter=Q(status="failure")),
        avg_latency_ms=Avg("latency_ms"),
        total_cost_usd=Sum("estimated_cost_usd"),
        total_tokens=Sum("total_tokens"),
    )

    total = stats["total_requests"] or 0
    stats["success_rate"] = (stats["successful"] or 0) / total if total > 0 else 0

    # Per-provider breakdown
    by_provider = (
        qs.values("provider")
        .annotate(
            count=Count("id"),
            success=Count("id", filter=Q(status="success")),
            avg_latency=Avg("latency_ms"),
            total_cost=Sum("estimated_cost_usd"),
        )
        .order_by("-count")
    )
    stats["by_provider"] = list(by_provider)

    return stats


def update_provider_health(hours: int = 1) -> int:
    """Aggregate execution logs into ProviderHealth records.

    Called periodically by a Celery task. Returns number of health records updated.
    """
    from .models import AIExecutionLog, ProviderHealth

    now = timezone.now()
    window_start = now - timedelta(hours=hours)
    window_end = now

    # Get unique (provider, feature_key) combinations in the window
    combinations = (
        AIExecutionLog.objects.filter(
            created_at__gte=window_start,
            created_at__lt=window_end,
        )
        .values_list("provider", "feature_key")
        .distinct()
    )

    updated = 0
    for provider, feature_key in combinations:
        logs = AIExecutionLog.objects.filter(
            provider=provider,
            feature_key=feature_key,
            created_at__gte=window_start,
            created_at__lt=window_end,
        )

        stats = logs.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status="success")),
            failed=Count("id", filter=Q(status="failure")),
            timeouts=Count("id", filter=Q(status="timeout")),
            avg_latency=Avg("latency_ms"),
            total_cost=Sum("estimated_cost_usd"),
            total_input_tokens=Sum("input_tokens"),
            total_output_tokens=Sum("output_tokens"),
        )

        total = stats["total"] or 0
        success_rate = (stats["success"] or 0) / total if total > 0 else 0

        # Calculate p95 latency (approximate using percentiles)
        latency_values = list(logs.values_list("latency_ms", flat=True).order_by("latency_ms"))
        p95_idx = int(len(latency_values) * 0.95) if latency_values else 0
        p99_idx = int(len(latency_values) * 0.99) if latency_values else 0
        p95_latency = latency_values[p95_idx] if latency_values else 0
        p99_latency = latency_values[p99_idx] if latency_values else 0

        ProviderHealth.objects.update_or_create(
            provider=provider,
            feature_key=feature_key,
            window_start=window_start,
            defaults={
                "window_end": window_end,
                "total_requests": total,
                "successful_requests": stats["success"] or 0,
                "failed_requests": stats["failed"] or 0,
                "timeout_requests": stats["timeouts"] or 0,
                "avg_latency_ms": int(stats["avg_latency"] or 0),
                "p95_latency_ms": p95_latency,
                "p99_latency_ms": p99_latency,
                "total_cost_usd": stats["total_cost"] or Decimal("0"),
                "total_input_tokens": stats["total_input_tokens"] or 0,
                "total_output_tokens": stats["total_output_tokens"] or 0,
                "success_rate": success_rate,
                "is_healthy": success_rate >= 0.95,
            },
        )
        updated += 1

    return updated


def calculate_estimated_cost(
    provider: str,
    model_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Decimal:
    """Calculate estimated cost for a provider/model combination.

    Returns Decimal cost in USD. Returns 0 if cost is unknown.
    Only includes providers with reliable, published pricing.
    """
    # Cost per 1K tokens (input, output) by provider/model
    COST_TABLE: dict[str, dict[str, tuple[Decimal, Decimal]]] = {
        # OpenAI models (USD per 1K tokens)
        "openai": {
            "gpt-4": (Decimal("0.03"), Decimal("0.06")),
            "gpt-4-turbo": (Decimal("0.01"), Decimal("0.03")),
            "gpt-4o": (Decimal("0.005"), Decimal("0.015")),
            "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
            "gpt-3.5-turbo": (Decimal("0.0005"), Decimal("0.0015")),
        },
        # Anthropic models
        "anthropic": {
            "claude-3-opus": (Decimal("0.015"), Decimal("0.075")),
            "claude-3-sonnet": (Decimal("0.003"), Decimal("0.015")),
            "claude-3-haiku": (Decimal("0.00025"), Decimal("0.00125")),
        },
    }

    provider_costs = COST_TABLE.get(provider.lower(), {})
    if not provider_costs:
        return Decimal("0")

    # Try exact match, then prefix match
    model_costs = provider_costs.get(model_name.lower())
    if not model_costs:
        for known_model, costs in provider_costs.items():
            if model_name.lower().startswith(known_model):
                model_costs = costs
                break

    if not model_costs:
        return Decimal("0")

    input_cost_per_1k, output_cost_per_1k = model_costs
    input_cost = (Decimal(str(input_tokens)) / Decimal("1000")) * input_cost_per_1k
    output_cost = (Decimal(str(output_tokens)) / Decimal("1000")) * output_cost_per_1k

    return input_cost + output_cost
