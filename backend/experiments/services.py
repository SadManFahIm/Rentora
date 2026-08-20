"""Experiment assignment, exposure and conversion services."""

from __future__ import annotations

import hashlib

from django.db import transaction

from analytics.services import record_event
from config.cache_utils import safe_cache_get, safe_cache_set

from .models import Experiment, ExperimentAssignment, ExperimentExposure, ExperimentVariant


def _identifier(user, anonymous_id: str | None, request) -> str:
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.id}"
    if anonymous_id:
        return f"anon:{anonymous_id}"
    meta = getattr(request, "META", {}) if request is not None else {}
    return f"ip:{meta.get('REMOTE_ADDR', 'unknown')}"


def _bucket(key: str, ident: str) -> int:
    # nosec B324: MD5 here is deterministic bucketing (stable variant assignment),
    # not a security primitive — an attacker gain from collisions is nil.
    digest = hashlib.md5(f"{key}:{ident}".encode()).hexdigest()[:8]  # nosec B324
    return int(digest, 16) % 100


def _pick_variant(experiment: Experiment) -> ExperimentVariant:
    variants = list(experiment.variants.all())
    if not variants:
        return None
    total = sum(v.weight for v in variants) or 1
    import random

    roll = random.randint(1, total)
    acc = 0
    for variant in variants:
        acc += variant.weight
        if roll <= acc:
            return variant
    return variants[0]


def get_variant(
    experiment_key: str,
    user=None,
    anonymous_id: str | None = None,
    request=None,
):
    """Deterministic variant assignment for a caller.

    Returns ``(experiment, variant_or_None)``. ``variant`` is None when the
    experiment is inactive/expired or the caller falls outside the traffic
    allocation (the product then renders the control / default experience).
    Assignment is persisted and reused for the same identifier.
    """
    try:
        experiment = Experiment.objects.filter(key=experiment_key).first()
    except Exception:
        return None, None
    if experiment is None or not experiment.is_running:
        return experiment, None

    ident = _identifier(user, anonymous_id, request)
    bucket = _bucket(experiment.key, ident)
    if bucket >= experiment.traffic_allocation:
        return experiment, None

    cached = safe_cache_get(f"experiment_assign:{experiment.key}:{ident}")
    if cached:
        variant = ExperimentVariant.objects.filter(pk=cached).first()
        if variant:
            return experiment, variant

    variant = _pick_variant(experiment)
    if variant is None:
        return experiment, None
    with transaction.atomic():
        ExperimentAssignment.objects.get_or_create(
            experiment=experiment,
            assignee_key=ident,
            defaults={
                "variant": variant,
                "user": user
                if user is not None and getattr(user, "is_authenticated", False)
                else None,
            },
        )
    safe_cache_set(f"experiment_assign:{experiment.key}:{ident}", variant.pk, timeout=3600)
    return experiment, variant


def record_exposure(
    experiment_key: str,
    variant_key: str,
    user=None,
    anonymous_id: str | None = None,
    request=None,
    context: dict | None = None,
) -> bool:
    """Record that the caller actually saw a variant (idempotent per caller).

    Returns False when the experiment/variant is unknown or the exposure was
    already recorded.
    """
    experiment = Experiment.objects.filter(key=experiment_key).first()
    variant = (
        ExperimentVariant.objects.filter(experiment=experiment, key=variant_key).first()
        if experiment
        else None
    )
    if experiment is None or variant is None:
        return False
    ident = _identifier(user, anonymous_id, request)
    _, created = ExperimentExposure.objects.get_or_create(
        experiment=experiment,
        assignee_key=ident,
        defaults={
            "variant": variant,
            "user": user if user is not None and getattr(user, "is_authenticated", False) else None,
            "context": context or {},
        },
    )
    return created


def record_conversion(
    experiment_key: str,
    variant_key: str,
    event_name: str,
    user=None,
    anonymous_id: str | None = None,
    request=None,
    context: dict | None = None,
) -> bool:
    """Attribute a conversion event to the caller's assigned variant.

    Ensures an exposure exists (a conversion implies the user saw the variant)
    and writes a standard analytics event tagged with the experiment context.
    """
    experiment = Experiment.objects.filter(key=experiment_key).first()
    if experiment is None:
        return False
    variant = ExperimentVariant.objects.filter(experiment=experiment, key=variant_key).first()
    if variant is None:
        variant = _pick_variant(experiment)
    if variant is None:
        return False
    record_exposure(
        experiment_key,
        variant.key,
        user=user,
        anonymous_id=anonymous_id,
        request=request,
        context=context or {},
    )
    record_event(
        user,
        event_name,
        category="experiment",
        properties={
            "experiment": experiment.key,
            "variant": variant.key,
            **(context or {}),
        },
    )
    return True


def active_experiments(user=None, request=None, anonymous_id: str | None = None) -> list[dict]:
    """Active experiments with the caller's assigned variant (for the UI)."""
    result = []
    for experiment in Experiment.objects.filter(status=Experiment.Status.ACTIVE):
        if not experiment.is_running:
            continue
        _exp, variant = get_variant(
            experiment.key, user=user, anonymous_id=anonymous_id, request=request
        )
        result.append(
            {
                "key": experiment.key,
                "name": experiment.name,
                "variant": variant.key if variant else None,
                "variants": [
                    {"key": v.key, "is_control": v.is_control} for v in experiment.variants.all()
                ],
            }
        )
    return result
