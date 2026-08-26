"""AI Intelligence Layer — Phase 18.1 + 18.2 + 18.3 services.

Provides:
- Feature registry management
- Prompt registry CRUD and versioning
- Execution log querying and aggregation
- Provider health monitoring
- Cost calculation utilities
- Evaluation dataset management (Phase 18.3)
- Evaluation run execution (Phase 18.3)
- Model/prompt comparison (Phase 18.3)
- Regression detection (Phase 18.3)

All functions are designed to be non-blocking and fail gracefully.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature Registry
# ---------------------------------------------------------------------------


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
    owner: str = "",
    status: str = "active",
    is_enabled: bool = True,
    default_provider: str = "",
    default_model: str = "",
    available_providers: list[str] | None = None,
    fallback_strategy: str = "none",
    feature_flag_key: str = "",
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
            "owner": owner,
            "status": status,
            "is_enabled": is_enabled,
            "default_provider": default_provider,
            "default_model": default_model,
            "available_providers": available_providers or [],
            "fallback_strategy": fallback_strategy,
            "feature_flag_key": feature_flag_key,
            "settings_key": settings_key,
            "estimated_cost_per_request": Decimal(str(estimated_cost_per_request)),
            "metadata": metadata or {},
        },
    )
    action = "Created" if created else "Updated"
    logger.info("%s AI feature: %s", action, feature_id)
    return feature


def is_feature_available(feature_key: str, user=None) -> bool:
    """Check if a feature is both enabled in the registry AND passes its flag.

    Returns True if the feature exists, is_enabled=True, and its linked
    feature flag (if any) is also active. Never raises.
    """
    try:
        feature = get_feature_registry(feature_key)
        if feature is None or not feature.is_enabled:
            return False
        if feature.feature_flag_key:
            from feature_flags.models import is_enabled as flag_is_enabled

            if not flag_is_enabled(feature.feature_flag_key, user=user):
                return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Prompt Registry
# ---------------------------------------------------------------------------

_VARIABLE_RE = re.compile(r"\{\{(\w+)\}\}")


def create_prompt(
    prompt_key: str,
    name: str,
    template: str,
    *,
    description: str = "",
    category: str = "other",
    feature_id: int | None = None,
    template_type: str = "template",
    default_model: str = "",
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    system_instructions: str = "",
    variables: dict | None = None,
    model_requirement: str = "",
    change_summary: str = "",
    created_by: Any = None,
) -> Any:
    """Create a new prompt with its first version (v1).

    Returns the AIPrompt instance. Raises on duplicate prompt_key.
    """
    from .models import AIFeatureRegistry, AIPrompt, AIPromptVersion

    feature = None
    if feature_id is not None:
        feature = AIFeatureRegistry.objects.filter(pk=feature_id).first()

    with transaction.atomic():
        prompt = AIPrompt.objects.create(
            prompt_key=prompt_key,
            name=name,
            description=description,
            category=category,
            feature=feature,
            template_type=template_type,
            default_model=default_model,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            status=AIPrompt.Status.DRAFT,
            created_by=created_by if created_by and created_by.is_authenticated else None,
        )

        # Create version 1 as the initial version (not auto-activated)
        AIPromptVersion.objects.create(
            prompt=prompt,
            version=1,
            template=template,
            system_instructions=system_instructions,
            variables=variables or {},
            model_requirement=model_requirement,
            status=AIPromptVersion.Status.INACTIVE,
            is_active=False,
            change_summary=change_summary or "Initial version",
            created_by=created_by if created_by and created_by.is_authenticated else None,
        )

    logger.info("Created prompt: %s", prompt_key)
    return prompt


def create_prompt_version(
    prompt_key: str,
    template: str,
    *,
    system_instructions: str = "",
    variables: dict | None = None,
    model_requirement: str = "",
    change_summary: str = "",
    created_by: Any = None,
) -> Any:
    """Create a new version for an existing prompt.

    Returns the new AIPromptVersion. The new version is NOT auto-activated.
    Raises ValueError if prompt does not exist.
    """
    from .models import AIPrompt, AIPromptVersion

    prompt = AIPrompt.objects.filter(prompt_key=prompt_key).first()
    if prompt is None:
        raise ValueError(f"Prompt not found: {prompt_key}")

    latest = prompt.versions.order_by("-version").first()
    next_version = (latest.version + 1) if latest else 1

    version = AIPromptVersion.objects.create(
        prompt=prompt,
        version=next_version,
        template=template,
        system_instructions=system_instructions,
        variables=variables or {},
        model_requirement=model_requirement,
        status=AIPromptVersion.Status.INACTIVE,
        is_active=False,
        change_summary=change_summary,
        created_by=created_by if created_by and created_by.is_authenticated else None,
    )
    logger.info("Created prompt version: %s:v%d", prompt_key, next_version)
    return version


def activate_prompt_version(
    prompt_key: str,
    version_number: int,
    *,
    activated_by: Any = None,
    request: Any = None,
) -> Any:
    """Activate a specific prompt version.

    Deactivates the currently active version (if any) and activates the
    specified version. Returns the activated version.
    Raises ValueError if version does not exist or prompt not found.
    """
    from .models import AIPromptVersion

    target = (
        AIPromptVersion.objects.select_related("prompt")
        .filter(prompt__prompt_key=prompt_key, version=version_number)
        .first()
    )
    if target is None:
        raise ValueError(f"Version not found: {prompt_key}:v{version_number}")

    with transaction.atomic():
        # Deactivate all currently active versions for this prompt
        AIPromptVersion.objects.filter(
            prompt=target.prompt,
            is_active=True,
        ).update(is_active=False, status=AIPromptVersion.Status.INACTIVE)

        # Activate the target version
        target.is_active = True
        target.status = AIPromptVersion.Status.ACTIVE
        target.save(update_fields=["is_active", "status"])

    # Audit log (non-blocking)
    try:
        from audit.services import log_action

        log_action(
            actor=activated_by,
            action="ai_intelligence.prompt_version.activated",
            target=target,
            request=request,
            detail={"prompt_key": prompt_key, "version": version_number},
        )
    except Exception:
        logger.debug("Audit log failed for prompt activation", exc_info=True)

    logger.info("Activated prompt version: %s:v%d", prompt_key, version_number)
    return target


def deactivate_prompt_version(
    prompt_key: str,
    *,
    deactivated_by: Any = None,
    request: Any = None,
) -> bool:
    """Deactivate the currently active version for a prompt.

    Returns True if a version was deactivated, False if none was active.
    """
    from .models import AIPromptVersion

    active = (
        AIPromptVersion.objects.select_related("prompt")
        .filter(prompt__prompt_key=prompt_key, is_active=True)
        .first()
    )
    if active is None:
        return False

    active.is_active = False
    active.status = AIPromptVersion.Status.INACTIVE
    active.save(update_fields=["is_active", "status"])

    try:
        from audit.services import log_action

        log_action(
            actor=deactivated_by,
            action="ai_intelligence.prompt_version.deactivated",
            target=active,
            request=request,
            detail={"prompt_key": prompt_key, "version": active.version},
        )
    except Exception:
        logger.debug("Audit log failed for prompt deactivation", exc_info=True)

    logger.info("Deactivated prompt version: %s:v%d", prompt_key, active.version)
    return True


def rollback_prompt(
    prompt_key: str,
    *,
    rolled_back_by: Any = None,
    request: Any = None,
) -> Any:
    """Rollback a prompt to its previous version.

    Finds the currently active version, deactivates it, and activates
    the version immediately before it (by version number).
    Returns the newly activated version, or raises ValueError if
    no rollback is possible (no active version or no previous version).
    """
    from .models import AIPromptVersion

    active = (
        AIPromptVersion.objects.select_related("prompt")
        .filter(prompt__prompt_key=prompt_key, is_active=True)
        .first()
    )
    if active is None:
        raise ValueError(f"No active version found for {prompt_key}")

    previous = (
        AIPromptVersion.objects.filter(
            prompt=active.prompt,
            version__lt=active.version,
        )
        .order_by("-version")
        .first()
    )
    if previous is None:
        raise ValueError(f"No previous version to rollback to for {prompt_key}")

    result = activate_prompt_version(
        prompt_key,
        previous.version,
        activated_by=rolled_back_by,
        request=request,
    )

    try:
        from audit.services import log_action

        log_action(
            actor=rolled_back_by,
            action="ai_intelligence.prompt_version.rollback",
            target=result,
            request=request,
            detail={
                "prompt_key": prompt_key,
                "from_version": active.version,
                "to_version": previous.version,
            },
        )
    except Exception:
        logger.debug("Audit log failed for prompt rollback", exc_info=True)

    return result


def get_prompt_template(prompt_key: str) -> tuple[str, dict] | None:
    """Get the active template and variables for a prompt.

    Returns (template, variables) tuple, or None if no active version.
    """
    from .models import AIPromptVersion

    active = (
        AIPromptVersion.objects.filter(
            prompt__prompt_key=prompt_key,
            is_active=True,
        )
        .select_related("prompt")
        .first()
    )
    if active is None:
        return None
    return active.template, active.variables


def render_prompt(
    prompt_key: str,
    context: dict[str, str],
) -> str:
    """Render a prompt template with the given context variables.

    Uses safe ``{{variable}}`` substitution. Validates that all required
    variables are present. Raises ValidationError on missing variables or
    template not found.
    """
    result = get_prompt_template(prompt_key)
    if result is None:
        raise ValidationError(f"No active prompt version for: {prompt_key}")

    template, variables = result

    # Find required variables (those without defaults)
    required = {
        name
        for name, defn in variables.items()
        if isinstance(defn, dict) and not defn.get("default")
    }
    provided = set(context.keys())
    missing = required - provided
    if missing:
        raise ValidationError(f"Missing required variables: {', '.join(sorted(missing))}")

    # Safe substitution — only {{word}} patterns
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return str(context.get(var_name, variables.get(var_name, {}).get("default", "")))

    return _VARIABLE_RE.sub(_replace, template)


def validate_prompt_variables(
    template: str,
    variables: dict,
) -> list[str]:
    """Extract declared variables from template and validate against schema.

    Returns a list of warning strings (empty if valid).
    """
    warnings: list[str] = []
    template_vars = set(_VARIABLE_RE.findall(template))
    schema_vars = set(variables.keys())

    undeclared = template_vars - schema_vars
    if undeclared:
        warnings.append(f"Template uses undeclared variables: {', '.join(sorted(undeclared))}")

    unused = schema_vars - template_vars
    if unused:
        warnings.append(f"Schema declares unused variables: {', '.join(sorted(unused))}")

    return warnings


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


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
    prompt_key: str = "",
    prompt_version: int = 0,
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
                prompt_key=prompt_key,
                prompt_version=prompt_version,
            )
            return log
    except Exception:
        logger.debug("Failed to log AI execution", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Provider Stats
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Provider Health
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Cost Estimation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Evaluation Framework (Phase 18.3)
# ---------------------------------------------------------------------------

from .evaluators import evaluate_case as _evaluate_case


def register_metric(
    metric_key: str,
    name: str,
    metric_type: str = "deterministic",
    category: str = "general",
    description: str = "",
    formula: str = "",
    is_higher_better: bool = True,
    default_threshold: float | None = None,
) -> Any:
    """Create or update an evaluation metric."""
    from .models import EvaluationMetric

    metric, _created = EvaluationMetric.objects.update_or_create(
        metric_key=metric_key,
        defaults={
            "name": name,
            "metric_type": metric_type,
            "category": category,
            "description": description,
            "formula": formula,
            "is_higher_better": is_higher_better,
            "default_threshold": default_threshold,
        },
    )
    return metric


def set_threshold(
    feature_id: str,
    metric_key: str,
    threshold_min: float | None = None,
    threshold_max: float | None = None,
) -> Any:
    """Set a per-feature quality threshold for a metric."""
    from .models import AIFeatureRegistry, EvaluationMetric, EvaluationThreshold

    feature = AIFeatureRegistry.objects.filter(feature_id=feature_id).first()
    if not feature:
        raise ValueError(f"Feature {feature_id} not found")
    metric = EvaluationMetric.objects.filter(metric_key=metric_key).first()
    if not metric:
        raise ValueError(f"Metric {metric_key} not found")
    threshold, _created = EvaluationThreshold.objects.update_or_create(
        feature=feature,
        metric=metric,
        defaults={
            "threshold_min": threshold_min,
            "threshold_max": threshold_max,
        },
    )
    return threshold


def get_thresholds(feature_id: str) -> list:
    """Return all thresholds for a feature."""
    from .models import AIFeatureRegistry, EvaluationThreshold

    feature = AIFeatureRegistry.objects.filter(feature_id=feature_id).first()
    if not feature:
        return []
    return list(EvaluationThreshold.objects.filter(feature=feature).select_related("metric"))


# ---------------------------------------------------------------------------
# Dataset Services
# ---------------------------------------------------------------------------


def create_dataset(
    dataset_key: str,
    name: str,
    feature_id: str | None = None,
    description: str = "",
    dataset_type: str = "synthetic",
    created_by=None,
) -> Any:
    """Create a new evaluation dataset (version 1)."""
    from .models import AIFeatureRegistry, EvaluationDataset

    feature = None
    if feature_id:
        feature = AIFeatureRegistry.objects.filter(feature_id=feature_id).first()
    dataset = EvaluationDataset.objects.create(
        dataset_key=dataset_key,
        name=name,
        description=description,
        feature=feature,
        dataset_type=dataset_type,
        version=1,
        created_by=created_by,
    )
    return dataset


def create_dataset_version(
    dataset_key: str,
    name: str | None = None,
    created_by=None,
) -> Any:
    """Create a new version of an existing dataset (clones cases)."""
    from .models import EvaluationCase, EvaluationDataset

    latest = EvaluationDataset.objects.filter(dataset_key=dataset_key).order_by("-version").first()
    if not latest:
        raise ValueError(f"Dataset {dataset_key} not found")
    new_version = latest.version + 1
    new_dataset = EvaluationDataset.objects.create(
        dataset_key=dataset_key,
        name=name or latest.name,
        description=latest.description,
        feature=latest.feature,
        dataset_type=latest.dataset_type,
        status="draft",
        version=new_version,
        created_by=created_by,
    )
    # Clone cases
    cases = list(
        EvaluationCase.objects.filter(dataset=latest).values(
            "case_id",
            "input",
            "expected_output",
            "expected_labels",
            "metadata",
            "evaluation_criteria",
        )
    )
    for case_data in cases:
        EvaluationCase.objects.create(dataset=new_dataset, **case_data)
    new_dataset.sample_count = len(cases)
    new_dataset.save(update_fields=["sample_count"])
    return new_dataset


def publish_dataset(dataset_key: str, version: int) -> Any:
    """Publish a dataset version (makes it immutable)."""
    from .models import EvaluationDataset

    dataset = EvaluationDataset.objects.filter(
        dataset_key=dataset_key,
        version=version,
    ).first()
    if not dataset:
        raise ValueError(f"Dataset {dataset_key} v{version} not found")
    if dataset.status not in ("draft", "review"):
        raise ValidationError(f"Cannot publish dataset in status '{dataset.status}'")
    dataset.status = "published"
    dataset.save(update_fields=["status"])
    return dataset


def archive_dataset(dataset_key: str, version: int) -> Any:
    """Archive a dataset version."""
    from .models import EvaluationDataset

    dataset = EvaluationDataset.objects.filter(
        dataset_key=dataset_key,
        version=version,
    ).first()
    if not dataset:
        raise ValueError(f"Dataset {dataset_key} v{version} not found")
    dataset.status = "archived"
    dataset.save(update_fields=["status"])
    return dataset


def add_cases(
    dataset_key: str,
    version: int,
    cases: list[dict],
) -> int:
    """Add evaluation cases to a dataset version. Returns count added.

    Each case dict should have: input, and optionally expected_output,
    expected_labels, metadata, evaluation_criteria, case_id.
    """
    from .models import EvaluationCase, EvaluationDataset

    dataset = EvaluationDataset.objects.filter(
        dataset_key=dataset_key,
        version=version,
    ).first()
    if not dataset:
        raise ValueError(f"Dataset {dataset_key} v{version} not found")
    if dataset.status == "published":
        raise ValidationError("Cannot add cases to a published dataset")
    created = 0
    for case_data in cases:
        EvaluationCase.objects.create(
            dataset=dataset,
            case_id=case_data.get("case_id", ""),
            input=case_data["input"],
            expected_output=case_data.get("expected_output"),
            expected_labels=case_data.get("expected_labels"),
            metadata=case_data.get("metadata", {}),
            evaluation_criteria=case_data.get("evaluation_criteria", {}),
        )
        created += 1
    dataset.sample_count = EvaluationCase.objects.filter(dataset=dataset).count()
    dataset.save(update_fields=["sample_count"])
    return created


def get_dataset(dataset_key: str, version: int | None = None):
    """Return a dataset, optionally at a specific version."""
    from .models import EvaluationDataset

    qs = EvaluationDataset.objects.filter(dataset_key=dataset_key)
    if version is not None:
        qs = qs.filter(version=version)
    return qs.order_by("-version").first()


# ---------------------------------------------------------------------------
# Evaluation Run Services
# ---------------------------------------------------------------------------


def create_evaluation_run(
    feature_id: str | None = None,
    dataset_key: str | None = None,
    dataset_version: int | None = None,
    prompt_key: str | None = None,
    prompt_version: int | None = None,
    model_name: str = "",
    provider: str = "",
    baseline_run_id: int | None = None,
    experiment_key: str = "",
    variant_key: str = "",
    max_cases: int = 1000,
    timeout_seconds: int = 3600,
    created_by=None,
) -> Any:
    """Create an evaluation run (pending status)."""
    from .models import (
        AIFeatureRegistry,
        EvaluationDataset,
        EvaluationRun,
    )

    feature = None
    if feature_id:
        feature = AIFeatureRegistry.objects.filter(feature_id=feature_id).first()
    dataset = None
    if dataset_key:
        ds_kwargs = {"dataset_key": dataset_key}
        if dataset_version:
            ds_kwargs["version"] = dataset_version
        dataset = EvaluationDataset.objects.filter(**ds_kwargs).order_by("-version").first()
    baseline_run = None
    if baseline_run_id:
        baseline_run = EvaluationRun.objects.filter(pk=baseline_run_id).first()

    run = EvaluationRun.objects.create(
        feature=feature,
        dataset=dataset,
        dataset_version=dataset.version if dataset else 0,
        prompt_version=prompt_version or 0,
        model_name=model_name,
        provider=provider,
        baseline_run=baseline_run,
        experiment_key=experiment_key,
        variant_key=variant_key,
        max_cases=max_cases,
        timeout_seconds=timeout_seconds,
        created_by=created_by,
    )

    # Snapshot prompt if provided
    if prompt_key:
        from .models import AIPrompt

        prompt = AIPrompt.objects.filter(prompt_key=prompt_key).first()
        if prompt:
            run.prompt = prompt
            run.prompt_version = prompt_version or (
                prompt.active_version.version if prompt.active_version else 0
            )
            run.save(update_fields=["prompt", "prompt_version"])

    return run


def execute_evaluation_run(run_id: int) -> dict:
    """Execute an evaluation run — evaluates all cases and computes metrics.

    Returns a summary dict with status, scores, and counts.
    """
    from .models import EvaluationCaseResult, EvaluationRun

    run = EvaluationRun.objects.filter(pk=run_id).first()
    if not run:
        return {"status": "error", "error": "Run not found"}
    if run.status not in ("pending",):
        return {"status": "error", "error": f"Run is {run.status}, expected pending"}

    run.status = "running"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    try:
        from .models import EvaluationCase as _EvaluationCase

        cases = _EvaluationCase.objects.filter(dataset=run.dataset)[: run.max_cases]
        total = 0
        passed = 0
        failed = 0
        errors = 0
        metric_totals: dict[str, float] = {}
        metric_counts: dict[str, int] = {}

        for case in cases:
            total += 1
            try:
                # Determine which evaluator to use
                feature_category = run.feature.category if run.feature else "general"
                case_criteria = case.evaluation_criteria or {}
                eval_category = case_criteria.get("evaluator", feature_category)

                result = _evaluate_case(
                    category=eval_category,
                    case_input=case.input,
                    actual_output=case.input,  # Default: use input as output for baseline
                    expected_output=case.expected_output,
                    case_metadata={**(case.metadata or {}), **case_criteria},
                )

                # Compute pass/fail based on thresholds
                case_passed = True
                if run.feature:
                    from .models import EvaluationThreshold

                    thresholds = EvaluationThreshold.objects.filter(
                        feature=run.feature,
                    ).select_related("metric")
                    for t in thresholds:
                        val = result.get(t.metric.metric_key)
                        if val is not None:
                            if t.threshold_min is not None and val < t.threshold_min:
                                case_passed = False
                            if t.threshold_max is not None and val > t.threshold_max:
                                case_passed = False

                composite_score = sum(result.values()) / len(result) if result else 0.0

                EvaluationCaseResult.objects.create(
                    run=run,
                    case=case,
                    input_data=case.input,
                    actual_output=case.input,  # Baseline: output = input
                    expected_output=case.expected_output,
                    metric_results=result,
                    passed=case_passed,
                    score=composite_score,
                )

                if case_passed:
                    passed += 1
                else:
                    failed += 1

                for k, v in result.items():
                    metric_totals[k] = metric_totals.get(k, 0.0) + v
                    metric_counts[k] = metric_counts.get(k, 0) + 1

            except Exception:
                logger.exception("Failed to evaluate case %s", case.pk)
                errors += 1
                EvaluationCaseResult.objects.create(
                    run=run,
                    case=case,
                    input_data=case.input,
                    passed=False,
                    score=0,
                    error_message="Evaluation failed",
                )

        # Compute aggregate scores
        metric_scores = {}
        for k in metric_totals:
            cnt = metric_counts.get(k, 1)
            metric_scores[k] = metric_totals[k] / cnt if cnt > 0 else 0.0

        overall_score = sum(metric_scores.values()) / len(metric_scores) if metric_scores else 0.0

        run.total_cases = total
        run.passed_cases = passed
        run.failed_cases = failed
        run.error_count = errors
        run.score = overall_score
        run.metric_scores = metric_scores
        run.status = "completed"
        run.completed_at = timezone.now()
        run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
        run.save(
            update_fields=[
                "total_cases",
                "passed_cases",
                "failed_cases",
                "error_count",
                "score",
                "metric_scores",
                "status",
                "completed_at",
                "duration_ms",
            ]
        )

        return {
            "status": "completed",
            "run_id": run.pk,
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "score": overall_score,
            "metric_scores": metric_scores,
        }

    except Exception:
        run.status = "failed"
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        logger.exception("Evaluation run %s failed", run_id)
        return {"status": "error", "error": "Run execution failed"}


def cancel_evaluation_run(run_id: int) -> bool:
    """Cancel a pending or running evaluation run."""
    from .models import EvaluationRun

    run = EvaluationRun.objects.filter(pk=run_id).first()
    if not run or run.status not in ("pending", "running"):
        return False
    run.status = "cancelled"
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at"])
    return True


# ---------------------------------------------------------------------------
# Comparison Services
# ---------------------------------------------------------------------------


def compare_runs(run_a_id: int, run_b_id: int) -> dict:
    """Compare two evaluation runs and produce a comparison report."""
    from .models import EvaluationRun

    run_a = EvaluationRun.objects.filter(pk=run_a_id).first()
    run_b = EvaluationRun.objects.filter(pk=run_b_id).first()
    if not run_a or not run_b:
        return {"error": "One or both runs not found"}

    metrics_a = run_a.metric_scores or {}
    metrics_b = run_b.metric_scores or {}

    all_metrics = sorted(set(metrics_a.keys()) | set(metrics_b.keys()))
    comparison = {}
    for m in all_metrics:
        va = metrics_a.get(m, 0.0)
        vb = metrics_b.get(m, 0.0)
        delta = vb - va
        comparison[m] = {
            "run_a": va,
            "run_b": vb,
            "delta": delta,
            "winner": "b" if delta > 0 else ("a" if delta < 0 else "tie"),
        }

    return {
        "run_a": {
            "id": run_a.pk,
            "score": run_a.score,
            "duration_ms": run_a.duration_ms,
            "total_cost_usd": str(run_a.total_cost_usd),
            "pass_rate": run_a.pass_rate,
        },
        "run_b": {
            "id": run_b.pk,
            "score": run_b.score,
            "duration_ms": run_b.duration_ms,
            "total_cost_usd": str(run_b.total_cost_usd),
            "pass_rate": run_b.pass_rate,
        },
        "metrics": comparison,
        "overall_winner": (
            "b" if run_b.score > run_a.score else ("a" if run_a.score > run_b.score else "tie")
        ),
    }


def compare_models(
    feature_id: str,
    model_a: str,
    model_b: str,
    dataset_key: str,
) -> dict:
    """Compare two models on the same feature and dataset.

    Returns the latest completed run for each model.
    """
    from .models import EvaluationRun

    def latest_run(model_name: str):
        return (
            EvaluationRun.objects.filter(
                feature__feature_id=feature_id,
                model_name=model_name,
                dataset__dataset_key=dataset_key,
                status="completed",
            )
            .order_by("-created_at")
            .first()
        )

    run_a = latest_run(model_a)
    run_b = latest_run(model_b)
    if not run_a and not run_b:
        return {"error": "No completed runs found for either model"}
    if not run_a:
        return {"error": f"No completed runs for model {model_a}"}
    if not run_b:
        return {"error": f"No completed runs for model {model_b}"}
    return compare_runs(run_a.pk, run_b.pk)


def compare_prompts(
    prompt_key: str,
    version_a: int,
    version_b: int,
    dataset_key: str,
) -> dict:
    """Compare two prompt versions on the same dataset."""
    from .models import EvaluationRun

    def latest_run(prompt_version: int):
        return (
            EvaluationRun.objects.filter(
                prompt__prompt_key=prompt_key,
                prompt_version=prompt_version,
                dataset__dataset_key=dataset_key,
                status="completed",
            )
            .order_by("-created_at")
            .first()
        )

    run_a = latest_run(version_a)
    run_b = latest_run(version_b)
    if not run_a and not run_b:
        return {"error": "No completed runs found for either prompt version"}
    if not run_a:
        return {"error": f"No completed runs for prompt v{version_a}"}
    if not run_b:
        return {"error": f"No completed runs for prompt v{version_b}"}
    return compare_runs(run_a.pk, run_b.pk)


def compare_with_baseline(run_id: int) -> dict:
    """Compare a run against its baseline."""
    from .models import EvaluationRun

    run = EvaluationRun.objects.filter(pk=run_id).first()
    if not run:
        return {"error": "Run not found"}
    if not run.baseline_run:
        return {"error": "No baseline set for this run"}
    return compare_runs(run.baseline_run_id, run_id)


# ---------------------------------------------------------------------------
# Regression Detection
# ---------------------------------------------------------------------------


def check_regression(run_id: int) -> dict:
    """Check if a run shows quality regression against thresholds or baseline.

    Returns a dict with regression status, details, and recommendation.
    """
    from .models import EvaluationRun, EvaluationThreshold

    run = EvaluationRun.objects.filter(pk=run_id).first()
    if not run:
        return {"error": "Run not found"}
    if run.status != "completed":
        return {"error": "Run is not completed"}

    regressions = []
    warnings = []
    metric_scores = run.metric_scores or {}

    # Check against feature thresholds
    if run.feature:
        thresholds = EvaluationThreshold.objects.filter(
            feature=run.feature,
        ).select_related("metric")
        for t in thresholds:
            val = metric_scores.get(t.metric.metric_key)
            if val is None:
                continue
            if t.threshold_min is not None and val < t.threshold_min:
                regressions.append(
                    {
                        "metric": t.metric.metric_key,
                        "value": val,
                        "threshold_min": t.threshold_min,
                        "severity": "regression",
                        "message": (
                            f"{t.metric.metric_key}={val:.4f} below minimum "
                            f"threshold {t.threshold_min}"
                        ),
                    }
                )
            elif t.threshold_max is not None and val > t.threshold_max:
                regressions.append(
                    {
                        "metric": t.metric.metric_key,
                        "value": val,
                        "threshold_max": t.threshold_max,
                        "severity": "regression",
                        "message": (
                            f"{t.metric.metric_key}={val:.4f} above maximum "
                            f"threshold {t.threshold_max}"
                        ),
                    }
                )

    # Check against baseline run
    if run.baseline_run and run.baseline_run.status == "completed":
        baseline_scores = run.baseline_run.metric_scores or {}
        for metric_key, value in metric_scores.items():
            baseline_val = baseline_scores.get(metric_key)
            if baseline_val is None:
                continue
            delta = value - baseline_val
            # Check if metric is higher-is-better
            from .models import EvaluationMetric

            em = EvaluationMetric.objects.filter(metric_key=metric_key).first()
            is_higher_better = em.is_higher_better if em else True
            pct_change = (delta / baseline_val * 100) if baseline_val != 0 else 0
            if (is_higher_better and delta < -0.05) or (not is_higher_better and delta > 0.05):
                regressions.append(
                    {
                        "metric": metric_key,
                        "baseline": baseline_val,
                        "current": value,
                        "delta": delta,
                        "pct_change": round(pct_change, 2),
                        "severity": "regression",
                        "message": (
                            f"{metric_key} degraded by {abs(pct_change):.1f}% "
                            f"({baseline_val:.4f} -> {value:.4f})"
                        ),
                    }
                )
            elif abs(pct_change) < 5:
                pass  # Within tolerance
            else:
                warnings.append(
                    {
                        "metric": metric_key,
                        "baseline": baseline_val,
                        "current": value,
                        "delta": delta,
                        "pct_change": round(pct_change, 2),
                        "message": f"{metric_key} changed by {abs(pct_change):.1f}%",
                    }
                )

    has_regression = len(regressions) > 0
    return {
        "run_id": run_id,
        "has_regression": has_regression,
        "regression_count": len(regressions),
        "regressions": regressions,
        "improvements": warnings,
        "recommendation": (
            "REVIEW REQUIRED — quality regression detected"
            if has_regression
            else "PASS — no regression detected"
        ),
    }


def get_latest_baselines(feature_id: str, limit: int = 5) -> list:
    """Return the latest completed evaluation runs for a feature as baselines."""
    from .models import EvaluationRun

    return list(
        EvaluationRun.objects.filter(
            feature__feature_id=feature_id,
            status="completed",
        ).order_by("-created_at")[:limit]
    )
