"""AI Intelligence Layer — Phase 18.1 models.

``AIFeatureRegistry`` tracks which AI features exist, their providers,
and configuration. This is the central registry for all AI capabilities.

``AIExecutionLog`` stores per-request telemetry: latency, tokens, cost,
success/failure, confidence, and fallback tracking. Uses UUID execution_id
for correlation across distributed systems.

``ProviderHealth`` tracks provider availability and failure rates over time.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AIFeatureRegistry(models.Model):
    """Central registry of all AI features in the system.

    Each row represents one AI capability (e.g., "liveness_detection",
    "face_match", "copilot", "chat_safety"). Used for:
    - Discovering available AI features
    - Tracking which providers serve each feature
    - Feature-flag gating for gradual rollout
    - Cost attribution per feature
    """

    class Category(models.TextChoices):
        FRAUD = "fraud", "Fraud Detection"
        KYC = "kyc", "Identity Verification"
        SEARCH = "search", "Search & Discovery"
        RECOMMENDATIONS = "recommendations", "Recommendations"
        PRICING = "pricing", "Pricing"
        CHAT = "chat", "Chat & Communication"
        COPILOT = "copilot", "AI Copilot"
        EMBEDDINGS = "embeddings", "Embeddings"
        OTHER = "other", "Other"

    feature_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique feature identifier (e.g. liveness_detection, face_match).",
    )
    name = models.CharField(
        max_length=200,
        help_text="Human-readable feature name.",
    )
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.OTHER,
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Master switch for this feature.",
    )
    default_provider = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Default provider name for this feature.",
    )
    available_providers = models.JSONField(
        default=list,
        blank=True,
        help_text='List of registered provider names (e.g. ["rules", "http"]).',
    )
    settings_key = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Django setting name that selects the active provider.",
    )
    estimated_cost_per_request = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Estimated cost per request in USD (0 if free).",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional feature configuration (provider-specific).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["feature_id"]
        verbose_name = "AI Feature"
        verbose_name_plural = "AI Features"

    def __str__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.feature_id} ({status})"


class AIExecutionLog(models.Model):
    """Per-request telemetry for all AI feature invocations.

    Lightweight, append-only log entry for every AI call. Uses UUID
    execution_id for correlation across distributed systems. Captures:
    - Provider/model/version tracking
    - Success/failure with failure type classification
    - Latency in milliseconds
    - Token usage (input/output) when available
    - Estimated cost calculation
    - Confidence score when available
    - Fallback chain tracking
    - Request correlation via execution_id
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        FALLBACK = "fallback", "Fallback"
        TIMEOUT = "timeout", "Timeout"
        RATE_LIMITED = "rate_limited", "Rate Limited"

    class FailureType(models.TextChoices):
        USER_FAILURE = "user_failure", "User Failure"
        PROVIDER_FAILURE = "provider_failure", "Provider Failure"
        SYSTEM_FAILURE = "system_failure", "System Failure"
        NONE = "none", "No Failure"

    execution_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Unique execution ID for request correlation.",
    )
    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.SET_NULL,
        null=True,
        related_name="execution_logs",
    )
    feature_key = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Feature identifier (denormalized for fast queries).",
    )

    # Provider tracking
    provider = models.CharField(
        max_length=100,
        help_text="Provider name that handled this request.",
    )
    provider_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Provider version if available.",
    )
    model_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="AI model name if applicable (e.g. gpt-4, sentence-transformers).",
    )
    model_version = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="AI model version if applicable.",
    )

    # Request context
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_execution_logs",
    )
    request_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="HTTP request ID for correlation (from RequestCorrelationMiddleware).",
    )

    # Outcome
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUCCESS,
        db_index=True,
    )
    failure_type = models.CharField(
        max_length=16,
        choices=FailureType.choices,
        default=FailureType.NONE,
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Sanitized error message (no secrets/PII).",
    )

    # Performance
    latency_ms = models.PositiveIntegerField(
        default=0,
        help_text="Provider execution latency in milliseconds.",
    )

    # Usage (where available)
    input_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Input tokens consumed (0 if not applicable).",
    )
    output_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Output tokens produced (0 if not applicable).",
    )
    total_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Total tokens (input + output, 0 if not applicable).",
    )

    # Cost
    estimated_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Estimated cost in USD (0 if free or unknown).",
    )

    # Quality
    confidence = models.FloatField(
        default=0,
        help_text="Provider confidence score (0.0-1.0, 0 if not applicable).",
    )

    # Fallback tracking
    is_fallback = models.BooleanField(
        default=False,
        help_text="True if this was a fallback attempt after primary failure.",
    )
    fallback_chain = models.JSONField(
        default=list,
        blank=True,
        help_text='List of providers tried before success (e.g. ["http", "rules"]).',
    )
    primary_provider = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="The primary provider that failed (if fallback was used).",
    )

    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional provider-specific telemetry (e.g. raw scores, flags).",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["feature_key", "created_at"],
                name="ai_exec_feature_time_idx",
            ),
            models.Index(
                fields=["provider", "status", "created_at"],
                name="ai_exec_provider_status_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="ai_exec_user_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.feature_key} via {self.provider} [{self.status}] "
            f"({self.latency_ms}ms) {self.created_at:%Y-%m-%d %H:%M}"
        )


class ProviderHealth(models.Model):
    """Aggregated provider health metrics over time windows.

    Updated periodically by a Celery task that aggregates AIExecutionLog
    entries. Used for:
    - Provider failover decisions
    - Health dashboards
    - Alerting on provider degradation
    """

    provider = models.CharField(
        max_length=100,
        db_index=True,
    )
    feature_key = models.CharField(
        max_length=100,
        db_index=True,
    )

    # Aggregated metrics
    total_requests = models.PositiveIntegerField(default=0)
    successful_requests = models.PositiveIntegerField(default=0)
    failed_requests = models.PositiveIntegerField(default=0)
    timeout_requests = models.PositiveIntegerField(default=0)

    # Performance
    avg_latency_ms = models.PositiveIntegerField(default=0)
    p95_latency_ms = models.PositiveIntegerField(default=0)
    p99_latency_ms = models.PositiveIntegerField(default=0)

    # Cost
    total_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)

    # Tokens
    total_input_tokens = models.PositiveIntegerField(default=0)
    total_output_tokens = models.PositiveIntegerField(default=0)

    # Health
    success_rate = models.FloatField(
        default=0,
        help_text="Success rate (0.0-1.0).",
    )
    is_healthy = models.BooleanField(
        default=True,
        help_text="False if success_rate drops below threshold.",
    )

    # Window
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-window_start"]
        indexes = [
            models.Index(
                fields=["provider", "feature_key", "window_start"],
                name="provider_health_lookup_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "feature_key", "window_start"],
                name="provider_health_window_unique",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.provider}/{self.feature_key} "
            f"[{'healthy' if self.is_healthy else 'DEGRADED'}] "
            f"({self.success_rate:.1%} success)"
        )
