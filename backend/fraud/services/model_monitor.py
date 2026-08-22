"""Model drift monitoring service (Phase 17, Stage 7).

Computes real-time performance metrics from recent fraud/trust predictions,
compares them against stored baselines, and triggers alerts + retrain
requests when drift is detected.

Metrics tracked:
- fraud_signal_rate: % of rooms with at least one fraud signal
- review_trust_avg: average review trust score
- photo_geo_mismatch_rate: % of rooms with GPS-tagged photos that mismatch
- review_anomaly_rate: % of rooms with review anomalies
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg
from django.utils import timezone

logger = logging.getLogger(__name__)

# Default drift thresholds — metric must stay within these bounds
DRIFT_THRESHOLDS = {
    "fraud_signal_rate": {
        "min": None,
        "max": 0.30,  # >30% rooms flagged = drift
        "baseline": 0.10,
    },
    "review_trust_avg": {
        "min": 50.0,  # avg trust below 50 = drift
        "max": None,
        "baseline": 70.0,
    },
    "photo_geo_mismatch_rate": {
        "min": None,
        "max": 0.15,  # >15% mismatch = drift
        "baseline": 0.05,
    },
}


def get_thresholds() -> dict:
    return getattr(settings, "MODEL_DRIFT_THRESHOLDS", DRIFT_THRESHOLDS)


def compute_fraud_signal_rate() -> float:
    """Percentage of rooms with at least one active fraud signal."""
    from fraud.models import FraudSignal
    from rooms.models import Room

    total = Room.objects.count()
    if total == 0:
        return 0.0

    flagged = FraudSignal.objects.values("report__room_id").distinct().count()
    return round(flagged / total, 4)


def compute_review_trust_avg() -> float:
    """Average trust score across all scored reviews."""
    from bookings.models import Review

    result = Review.objects.filter(trust_score__isnull=False).aggregate(avg=Avg("trust_score"))
    return round(result["avg"] or 0.0, 2)


def compute_photo_geo_mismatch_rate() -> float:
    """Percentage of rooms with GPS-tagged photos that have a geo mismatch."""
    from fraud.models import FraudSignal
    from rooms.models import Room

    total_with_gps = Room.objects.filter(images__photo_lat__isnull=False).distinct().count()
    if total_with_gps == 0:
        return 0.0

    mismatched = (
        FraudSignal.objects.filter(detector="photo_geo_mismatch")
        .values("report__room_id")
        .distinct()
        .count()
    )

    return round(mismatched / total_with_gps, 4)


def record_drift_metric(
    model_version, metric_name: str, value: float, window_hours: int = 24
) -> dict:
    """Record a drift metric and check for threshold breach.

    Returns the DriftMetric record data.
    """
    from ml_models.models import DriftMetric

    thresholds = get_thresholds()
    t = thresholds.get(metric_name, {})
    baseline = t.get("baseline")
    threshold_min = t.get("min")
    threshold_max = t.get("max")

    breached = False
    if threshold_min is not None and value < threshold_min:
        breached = True
    if threshold_max is not None and value > threshold_max:
        breached = True

    now = timezone.now()
    metric = DriftMetric.objects.create(
        model_version=model_version,
        metric_name=metric_name,
        value=value,
        baseline_value=baseline,
        threshold_min=threshold_min,
        threshold_max=threshold_max,
        threshold_breached=breached,
        window_start=now - timedelta(hours=window_hours),
        window_end=now,
        sample_count=0,
    )

    if breached:
        _trigger_retrain_request(model_version, metric_name, value, t)

    return {
        "metric_id": metric.pk,
        "metric_name": metric_name,
        "value": value,
        "baseline": baseline,
        "breached": breached,
    }


def _trigger_retrain_request(model_version, metric_name: str, value: float, thresholds: dict):
    """Create a retrain request when drift is detected."""
    from ml_models.models import RetrainRequest

    # Don't create duplicate pending requests
    existing = RetrainRequest.objects.filter(
        model_version=model_version,
        status=RetrainRequest.Status.PENDING,
        reason__icontains=f"drift detected: {metric_name}",
    ).exists()
    if existing:
        return

    reason_parts = [f"Drift detected: {metric_name}={value:.4f}"]
    if thresholds.get("baseline"):
        reason_parts.append(f"baseline={thresholds['baseline']}")
    if thresholds.get("max") and value > thresholds["max"]:
        reason_parts.append(f"exceeds max={thresholds['max']}")
    if thresholds.get("min") and value < thresholds["min"]:
        reason_parts.append(f"below min={thresholds['min']}")

    RetrainRequest.objects.create(
        model_version=model_version,
        reason=". ".join(reason_parts),
    )
    logger.warning(
        "Drift retrain request created for %s: %s",
        model_version.name,
        reason_parts[0],
    )


def check_all_drift() -> dict:
    """Run all drift checks and return summary.

    Called by the daily check_model_drift task.
    """
    from ml_models.models import ModelVersion

    active_models = ModelVersion.objects.filter(status=ModelVersion.Status.ACTIVE)
    if not active_models.exists():
        # Fall back to most recent model per name
        from django.db.models import OuterRef, Subquery

        latest_ids = (
            ModelVersion.objects.filter(name=OuterRef("name")).order_by("-version").values("pk")[:1]
        )
        active_models = ModelVersion.objects.filter(pk__in=Subquery(latest_ids))

    # If still no models, create a default one for tracking
    if not active_models.exists():
        mv, _ = ModelVersion.objects.get_or_create(
            name="fraud_system",
            version="1.0.0",
            defaults={
                "description": "Overall fraud detection system",
                "status": ModelVersion.Status.ACTIVE,
            },
        )
        active_models = ModelVersion.objects.filter(pk=mv.pk)

    metrics_computed = []
    breaches = []

    for mv in active_models:
        # Compute all metrics
        metric_fns = {
            "fraud_signal_rate": compute_fraud_signal_rate,
            "review_trust_avg": compute_review_trust_avg,
            "photo_geo_mismatch_rate": compute_photo_geo_mismatch_rate,
        }

        for name, fn in metric_fns.items():
            value = fn()
            result = record_drift_metric(mv, name, value)
            metrics_computed.append(result)
            if result["breached"]:
                breaches.append(result)

    # Alert admins if breaches found
    if breaches:
        _alert_admins(breaches)

    return {
        "metrics_computed": len(metrics_computed),
        "breaches": len(breaches),
        "details": metrics_computed,
    }


def _alert_admins(breaches: list):
    """Send admin alerts for drift breaches."""
    try:
        from notifications.utils import create_notification
        from users.models import User

        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            for breach in breaches[:5]:
                create_notification(
                    user=admin,
                    subject=f"Model drift: {breach['metric_name']} breached",
                    body=(
                        f"{breach['metric_name']}={breach['value']:.4f} "
                        f"(baseline={breach['baseline']}). "
                        "Retrain request has been created."
                    ),
                    category="model_drift",
                    url="/admin/ml_models/driftmetric/",
                )
    except Exception:
        logger.exception("Failed to send drift alerts")
