"""AI Intelligence Layer — Phase 18.1 + 18.2 models.

``AIFeatureRegistry`` tracks which AI features exist, their providers,
and configuration. This is the central registry for all AI capabilities.

``AIPrompt`` and ``AIPromptVersion`` provide a versioned prompt/template
registry for all AI features. Templates are immutable once created.

``AIExecutionLog`` stores per-request telemetry: latency, tokens, cost,
success/failure, confidence, and fallback tracking. Uses UUID execution_id
for correlation across distributed systems.

``ProviderHealth`` tracks provider availability and failure rates over time.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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
    status = models.CharField(
        max_length=16,
        choices=[
            ("active", "Active"),
            ("beta", "Beta"),
            ("deprecated", "Deprecated"),
            ("disabled", "Disabled"),
        ],
        default="active",
        help_text="Feature lifecycle status.",
    )
    owner = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Team or person responsible for this feature.",
    )
    default_provider = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Default provider name for this feature.",
    )
    default_model = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Default model name (e.g. gpt-4o, sentence-transformers).",
    )
    available_providers = models.JSONField(
        default=list,
        blank=True,
        help_text='List of registered provider names (e.g. ["rules", "http"]).',
    )
    fallback_strategy = models.CharField(
        max_length=32,
        choices=[
            ("none", "No fallback"),
            ("rules", "Fall back to rules engine"),
            ("cache", "Fall back to cached result"),
            ("degraded", "Serve degraded response"),
        ],
        default="none",
        help_text="Fallback behavior when primary provider fails.",
    )
    feature_flag_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Optional linked feature flag key for gating.",
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
        return f"{self.feature_id} ({self.status})"


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

    # Prompt tracking (Phase 18.2)
    prompt_key = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Prompt registry key if applicable.",
    )
    prompt_version = models.PositiveIntegerField(
        default=0,
        help_text="Prompt version number (0 if not applicable).",
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


# ---------------------------------------------------------------------------
# Prompt Registry (Phase 18.2)
# ---------------------------------------------------------------------------

# Reserved words that must not appear in prompt templates (security).
_FORBIDDEN_PATTERNS = (
    "API_KEY",
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "PRIVATE_KEY",
    "AWS_",
    "OPENAI_API",
    "ANTHROPIC_API",
)


def _validate_template_safety(template: str) -> None:
    """Reject templates that contain secret-like strings."""
    upper = template.upper()
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in upper:
            raise ValidationError(
                f"Template contains a forbidden pattern ({pattern}). "
                "API keys and secrets must not be stored in prompt templates."
            )


class AIPrompt(models.Model):
    """A versioned prompt/template container for an AI feature.

    Each ``AIPrompt`` has a unique ``prompt_key`` (e.g. ``ai.copilot.search``)
    and contains one or more immutable ``AIPromptVersion`` records. Only one
    version can be active at a time.

    ``template_type`` classifies the content:
    - ``template``: LLM prompt with ``{{variable}}`` placeholders.
    - ``rules``: Deterministic rule set (keyword lists, regex, thresholds).
    - ``config``: General configuration (feature params, thresholds, URLs).
    """

    class TemplateType(models.TextChoices):
        TEMPLATE = "template", "LLM Prompt Template"
        RULES = "rules", "Deterministic Rules"
        CONFIG = "config", "Configuration"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DRAFT = "draft", "Draft"
        ARCHIVED = "archived", "Archived"

    prompt_key = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Stable identifier (e.g. ai.copilot.search).",
    )
    name = models.CharField(
        max_length=200,
        help_text="Human-readable prompt name.",
    )
    description = models.TextField(
        blank=True,
        default="",
    )
    category = models.CharField(
        max_length=32,
        choices=AIFeatureRegistry.Category.choices,
        default=AIFeatureRegistry.Category.OTHER,
    )
    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prompts",
    )

    # Template structure
    template_type = models.CharField(
        max_length=16,
        choices=TemplateType.choices,
        default=TemplateType.TEMPLATE,
    )
    default_model = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Required model/capability (e.g. gpt-4o, sentence-transformers).",
    )
    input_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Expected input variables and their types.",
    )
    output_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Expected output format description.",
    )

    # Lifecycle
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_prompts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["prompt_key"]
        verbose_name = "AI Prompt"
        verbose_name_plural = "AI Prompts"

    def __str__(self) -> str:
        return f"{self.prompt_key} ({self.status})"

    @property
    def active_version(self):
        """Return the currently active version, or None."""
        return self.versions.filter(is_active=True).first()

    @property
    def latest_version(self):
        """Return the highest version number, or None."""
        return self.versions.order_by("-version").first()


class AIPromptVersion(models.Model):
    """An immutable version of an AI prompt template.

    Once created, a version is never modified. Changes produce a new version.
    Only one version per prompt can be ``is_active=True`` at any time.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        DEPRECATED = "deprecated", "Deprecated"

    prompt = models.ForeignKey(
        AIPrompt,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField(
        help_text="Version number (auto-incrementing per prompt).",
    )

    # Content (immutable after creation)
    template = models.TextField(
        help_text="The prompt template, rule set, or configuration.",
    )
    system_instructions = models.TextField(
        blank=True,
        default="",
        help_text="System-level instructions (for LLM templates).",
    )
    variables = models.JSONField(
        default=dict,
        blank=True,
        help_text="Variable definitions with types, defaults, and descriptions.",
    )
    model_requirement = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Required model or capability for this version.",
    )

    # Lifecycle
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.INACTIVE,
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Only one version per prompt can be active.",
    )
    change_summary = models.TextField(
        blank=True,
        default="",
        help_text="Why this version was created.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_prompt_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["prompt", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["prompt", "version"],
                name="ai_prompt_version_unique",
            ),
        ]
        verbose_name = "AI Prompt Version"
        verbose_name_plural = "AI Prompt Versions"

    def __str__(self) -> str:
        return f"{self.prompt.prompt_key}:v{self.version} ({self.status})"

    def clean(self):
        super().clean()
        _validate_template_safety(self.template)
        _validate_template_safety(self.system_instructions)
