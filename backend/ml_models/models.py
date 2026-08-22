"""ML model version tracking and drift monitoring (Phase 17 — Stage 2).

``ModelVersion`` tracks every deployed model variant: name, version string,
training date, performance metrics, and active/deprecated status.

``DriftMetric`` stores time-series metrics for detecting when a model's
predictions diverge from its training baseline. Each row is one metric
(e.g. "accuracy", "precision", "recall") over one time window.

``RetrainRequest`` records retrain triggers: who requested it, why, and
whether it completed. Provides a lightweight audit trail for model lifecycle
without introducing a full MLOps pipeline.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ModelVersion(models.Model):
    """One deployed model variant (e.g. ``review_trust_v2``, ``photo_geo_v1``)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEPRECATED = "deprecated", "Deprecated"
        EXPERIMENTAL = "experimental", "Experimental"

    name = models.CharField(
        max_length=100,
        help_text="Model identifier (e.g. review_trust, photo_geo, scam_graph).",
    )
    version = models.CharField(
        max_length=50,
        help_text="Version string (e.g. 1.0.0, 2026-08-22).",
    )
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EXPERIMENTAL)
    training_date = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Performance metrics at training time (accuracy, precision, recall, f1, etc.).",
    )
    artifacts_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Path to model artifacts (if self-hosted). Empty for provider-based models.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "version"],
                name="ml_model_version_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version} [{self.status}]"


class DriftMetric(models.Model):
    """One metric measurement for a model version over a time window.

    Used to detect when a model's real-world performance degrades below
    its training baseline. The ``threshold_breached`` flag is set when
    the metric falls outside the acceptable range, triggering alerts.
    """

    model_version = models.ForeignKey(
        ModelVersion, on_delete=models.CASCADE, related_name="drift_metrics"
    )
    metric_name = models.CharField(
        max_length=100,
        help_text="Metric identifier (e.g. accuracy, precision, recall, f1, latency_p95).",
    )
    value = models.FloatField(
        help_text="Measured value for this metric in the time window.",
    )
    baseline_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Training-time baseline for comparison.",
    )
    threshold_min = models.FloatField(
        null=True,
        blank=True,
        help_text="Lower bound — breached if value drops below this.",
    )
    threshold_max = models.FloatField(
        null=True,
        blank=True,
        help_text="Upper bound — breached if value exceeds this.",
    )
    threshold_breached = models.BooleanField(
        default=False,
        help_text="True if value is outside the acceptable range.",
    )
    window_start = models.DateTimeField(
        help_text="Start of the measurement window.",
    )
    window_end = models.DateTimeField(
        help_text="End of the measurement window.",
    )
    sample_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of data points in this window.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["model_version", "metric_name", "created_at"],
                name="drift_metric_lookup_idx",
            ),
            models.Index(
                fields=["threshold_breached", "created_at"],
                name="drift_breached_idx",
            ),
        ]

    def __str__(self) -> str:
        status = "BREACHED" if self.threshold_breached else "ok"
        return f"{self.model_version.name} {self.metric_name}={self.value:.4f} [{status}]"


class RetrainRequest(models.Model):
    """A request to retrain a model version, with lifecycle tracking.

    Requests are created by drift monitoring (automatic) or by admins
    (manual). The actual training happens outside this system; this model
    tracks the request lifecycle for audit purposes.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.CASCADE,
        related_name="retrain_requests",
        null=True,
        blank=True,
        help_text="The model version to retrain (null for brand-new model training).",
    )
    reason = models.TextField(
        help_text="Why this retrain was triggered (drift alert, manual request, scheduled).",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retrain_requests",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Admin notes or failure details.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        target = self.model_version or "new-model"
        return f"Retrain {target} [{self.status}]"
