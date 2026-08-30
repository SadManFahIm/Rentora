"""AI Intelligence Layer — Phase 18.1 + 18.2 + 18.3 models.

``AIFeatureRegistry`` tracks which AI features exist, their providers,
and configuration. This is the central registry for all AI capabilities.

``AIPrompt`` and ``AIPromptVersion`` provide a versioned prompt/template
registry for all AI features. Templates are immutable once created.

``AIExecutionLog`` stores per-request telemetry: latency, tokens, cost,
success/failure, confidence, and fallback tracking. Uses UUID execution_id
for correlation across distributed systems.

``ProviderHealth`` tracks provider availability and failure rates over time.

Phase 18.3 adds the AI Evaluation Framework:
- ``EvaluationMetric`` defines available metric types (F1, NDCG, etc.)
- ``EvaluationDataset`` is a versioned golden dataset container.
- ``EvaluationCase`` is an individual test case within a dataset.
- ``EvaluationThreshold`` stores per-feature quality thresholds.
- ``EvaluationRun`` records an evaluation execution with aggregate results.
- ``EvaluationCaseResult`` stores per-case evaluation outcomes.
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


# ---------------------------------------------------------------------------
# Evaluation Framework (Phase 18.3)
# ---------------------------------------------------------------------------


class EvaluationMetric(models.Model):
    """Defines a metric type that can be used across evaluation runs.

    Metrics are reusable across features. Each metric has a type
    (deterministic, heuristic, llm_judge, human) and a category
    (search, classification, fraud, prediction, llm, general).
    """

    class MetricType(models.TextChoices):
        DETERMINISTIC = "deterministic", "Deterministic"
        HEURISTIC = "heuristic", "Heuristic"
        LLM_JUDGE = "llm_judge", "LLM-as-Judge"
        HUMAN = "human", "Human Evaluation"

    class Category(models.TextChoices):
        SEARCH = "search", "Search"
        RECOMMENDATION = "recommendation", "Recommendation"
        CLASSIFICATION = "classification", "Classification"
        FRAUD = "fraud", "Fraud Detection"
        PREDICTION = "prediction", "Prediction"
        LLM = "llm", "LLM Quality"
        GENERAL = "general", "General"

    metric_key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Stable identifier (e.g. f1, ndcg, precision_at_k).",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    metric_type = models.CharField(
        max_length=16,
        choices=MetricType.choices,
        default=MetricType.DETERMINISTIC,
    )
    category = models.CharField(
        max_length=16,
        choices=Category.choices,
        default=Category.GENERAL,
    )
    formula = models.TextField(
        blank=True,
        default="",
        help_text="Description of how this metric is computed.",
    )
    is_higher_better = models.BooleanField(
        default=True,
        help_text="True if higher values are better (False for MAE, RMSE, etc.).",
    )
    default_threshold = models.FloatField(
        null=True,
        blank=True,
        help_text="Default quality threshold for this metric (nullable).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["metric_key"]

    def __str__(self) -> str:
        return f"{self.name} ({self.metric_type})"


class EvaluationDataset(models.Model):
    """A versioned golden dataset for AI evaluation.

    Datasets are versioned containers of ``EvaluationCase`` records.
    Each version is immutable once published. New versions can be
    created by cloning an existing one.

    Datasets must NOT contain production user data. Use synthetic,
    anonymized, or manually reviewed samples only.
    """

    class DatasetType(models.TextChoices):
        SYNTHETIC = "synthetic", "Synthetic"
        ANONYMIZED = "anonymized", "Anonymized"
        MANUAL_REVIEW = "manual_review", "Manually Reviewed"
        APPROVED = "approved", "Approved"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "In Review"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    dataset_key = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Stable identifier (e.g. search.uttara.relevance).",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_datasets",
    )
    dataset_type = models.CharField(
        max_length=16,
        choices=DatasetType.choices,
        default=DatasetType.SYNTHETIC,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Version number (immutable once published).",
    )
    sample_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of evaluation cases (denormalized).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_datasets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["dataset_key", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset_key", "version"],
                name="eval_dataset_version_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.dataset_key} v{self.version} ({self.status})"


class EvaluationCase(models.Model):
    """An individual test case within a golden dataset.

    Cases are immutable within a published dataset version. Each case
    has an input, optional expected output/labels, and evaluation criteria.
    """

    dataset = models.ForeignKey(
        EvaluationDataset,
        on_delete=models.CASCADE,
        related_name="cases",
    )
    case_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional stable ID within the dataset (e.g. 'case_001').",
    )
    input = models.JSONField(
        help_text="Test input data.",
    )
    expected_output = models.JSONField(
        null=True,
        blank=True,
        help_text="Expected/reference output (nullable for open-ended tasks).",
    )
    expected_labels = models.JSONField(
        null=True,
        blank=True,
        help_text="Expected labels for classification (e.g. ['fraud', 'high_risk']).",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Category, difficulty, tags, etc.",
    )
    evaluation_criteria = models.JSONField(
        default=dict,
        blank=True,
        help_text="What to measure for this case (metric overrides, thresholds).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dataset", "id"]
        indexes = [
            models.Index(
                fields=["dataset", "created_at"],
                name="eval_case_dataset_idx",
            ),
        ]

    def __str__(self) -> str:
        case_label = self.case_id or str(self.pk)
        return f"{self.dataset.dataset_key}:{case_label}"


class EvaluationThreshold(models.Model):
    """Per-feature quality thresholds for evaluation metrics.

    Allows feature-specific thresholds (e.g. fraud F1 >= 0.90,
    search NDCG >= 0.80). Do not hard-code universal thresholds.
    """

    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.CASCADE,
        related_name="evaluation_thresholds",
    )
    metric = models.ForeignKey(
        EvaluationMetric,
        on_delete=models.CASCADE,
        related_name="thresholds",
    )
    threshold_min = models.FloatField(
        null=True,
        blank=True,
        help_text="Minimum acceptable value (nullable = no min).",
    )
    threshold_max = models.FloatField(
        null=True,
        blank=True,
        help_text="Maximum acceptable value (nullable = no max).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feature", "metric"],
                name="eval_threshold_feature_metric_unique",
            ),
        ]

    def __str__(self) -> str:
        parts = [self.feature.feature_id, self.metric.metric_key]
        if self.threshold_min is not None:
            parts.append(f">={self.threshold_min}")
        if self.threshold_max is not None:
            parts.append(f"<={self.threshold_max}")
        return " ".join(parts)


class EvaluationRun(models.Model):
    """Records an evaluation execution against a dataset.

    Tracks feature, dataset version, provider/model, prompt version,
    aggregate results, cost, and duration. Supports baseline comparison
    and experiment integration.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    run_key = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Unique run ID for correlation.",
    )

    # Context
    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    dataset = models.ForeignKey(
        EvaluationDataset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    dataset_version = models.PositiveIntegerField(
        default=0,
        help_text="Snapshot of dataset version at run time.",
    )
    prompt = models.ForeignKey(
        "AIPrompt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    prompt_version = models.PositiveIntegerField(
        default=0,
        help_text="Snapshot of prompt version at run time.",
    )
    model_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
    )
    provider = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    # Comparison
    baseline_run = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparison_runs",
        help_text="Baseline run for comparison (nullable).",
    )

    # Experiment integration
    experiment_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Experiment key for A/B comparison (nullable).",
    )
    variant_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Experiment variant key (nullable).",
    )

    # Execution
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(
        default=0,
        help_text="Total execution time in milliseconds.",
    )

    # Results
    total_cases = models.PositiveIntegerField(default=0)
    passed_cases = models.PositiveIntegerField(default=0)
    failed_cases = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    score = models.FloatField(
        default=0,
        help_text="Composite score (0.0-1.0, weighted average of metrics).",
    )
    metric_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text='Per-metric scores (e.g. {"f1": 0.91, "precision": 0.88}).',
    )

    # Cost safeguards
    total_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
    )
    max_cases = models.PositiveIntegerField(
        default=1000,
        help_text="Maximum cases to evaluate (cost safeguard).",
    )
    timeout_seconds = models.PositiveIntegerField(
        default=3600,
        help_text="Maximum execution time in seconds.",
    )

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["feature", "created_at"],
                name="eval_run_feature_time_idx",
            ),
            models.Index(
                fields=["status", "created_at"],
                name="eval_run_status_time_idx",
            ),
        ]

    def __str__(self) -> str:
        feature_label = self.feature.feature_id if self.feature else "unspecified"
        return (
            f"Run {str(self.run_key)[:8]} ({feature_label}) [{self.status}] score={self.score:.3f}"
        )

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases


class EvaluationCaseResult(models.Model):
    """Per-case result from an evaluation run.

    Stores the actual output, expected output, per-metric scores,
    and pass/fail status for each case evaluated.
    """

    run = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="case_results",
    )
    case = models.ForeignKey(
        EvaluationCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
    )

    # Data snapshots
    input_data = models.JSONField(
        help_text="Snapshot of the input at evaluation time.",
    )
    actual_output = models.JSONField(
        null=True,
        blank=True,
        help_text="AI output for this case.",
    )
    expected_output = models.JSONField(
        null=True,
        blank=True,
        help_text="Snapshot of expected output at evaluation time.",
    )

    # Results
    metric_results = models.JSONField(
        default=dict,
        blank=True,
        help_text='Per-metric scores (e.g. {"f1": 0.95, "precision": 0.92}).',
    )
    passed = models.BooleanField(
        default=False,
        db_index=True,
    )
    score = models.FloatField(
        default=0,
        help_text="Composite score for this case.",
    )
    confidence = models.FloatField(
        default=0,
        help_text="Model confidence for this case (0.0-1.0).",
    )

    # Performance
    latency_ms = models.PositiveIntegerField(default=0)

    # Errors
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Sanitized error message if case failed.",
    )

    # Traceability
    evaluator_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Version of the evaluator used.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "id"]
        indexes = [
            models.Index(
                fields=["run", "passed"],
                name="eval_caseresult_run_pass_idx",
            ),
            models.Index(
                fields=["run", "score"],
                name="eval_caseresult_run_score_idx",
            ),
        ]

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"Run {str(self.run.run_key)[:8]} Case {self.pk} [{status}]"


# ===========================================================================
# Phase 18.4 — AI Intelligence Alerts
# ===========================================================================


class AIAlertRule(models.Model):
    """A configurable rule that watches an AI metric against a threshold.

    Rules are evaluated periodically by ``ai_intelligence.evaluate_alert_rules``
    (Celery beat). Anti-noise controls:

    - ``consecutive_checks`` — only trigger once breached for N consecutive
      evaluation runs (tracks ``breach_count``).
    - ``cooldown_minutes`` — do not re-trigger the same rule+scope for the
      cooldown window after an alert fires.
    - ``dedup_key`` — alerts are deduplicated per (rule, feature, provider,
      model) scope.
    """

    class AlertType(models.TextChoices):
        RELIABILITY = "reliability", "Reliability"
        PERFORMANCE = "performance", "Performance"
        QUALITY = "quality", "Quality"
        COST = "cost", "Cost"
        DRIFT = "drift", "Drift"
        AVAILABILITY = "availability", "Availability"

    class Metric(models.TextChoices):
        ERROR_RATE = "error_rate", "Error rate"
        TIMEOUT_RATE = "timeout_rate", "Timeout rate"
        FALLBACK_RATE = "fallback_rate", "Fallback rate"
        SUCCESS_RATE = "success_rate", "Success rate"
        AVG_LATENCY = "avg_latency", "Average latency (ms)"
        P95_LATENCY = "p95_latency", "P95 latency (ms)"
        DAILY_COST = "daily_cost", "Daily estimated cost (USD)"
        COST_PER_EXECUTION = "cost_per_execution", "Cost per execution (USD)"
        EVALUATION_SCORE = "evaluation_score", "Evaluation score"
        DRIFT_BREACH = "drift_breach", "Model drift breach"

    class Operator(models.TextChoices):
        GT = "gt", ">"
        GTE = "gte", ">="
        LT = "lt", "<"
        LTE = "lte", "<="

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    rule_key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique rule identifier (e.g. copilot_error_rate).",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    alert_type = models.CharField(
        max_length=30,
        choices=AlertType.choices,
        default=AlertType.RELIABILITY,
    )
    metric = models.CharField(
        max_length=40,
        choices=Metric.choices,
        help_text="The metric this rule watches.",
    )
    operator = models.CharField(
        max_length=10,
        choices=Operator.choices,
        default=Operator.GT,
    )
    threshold_value = models.FloatField(help_text="Threshold the metric is compared against.")
    # Scope (all optional = global rule)
    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.CASCADE,
        related_name="alert_rules",
        null=True,
        blank=True,
    )
    provider = models.CharField(max_length=100, blank=True, default="")
    model_name = models.CharField(max_length=200, blank=True, default="")
    # Anti-noise controls
    duration_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Look-back window (minutes) used to compute the metric.",
    )
    consecutive_checks = models.PositiveIntegerField(
        default=1,
        help_text="Trigger only after this many consecutive breaches.",
    )
    cooldown_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Minimum minutes between alerts for the same scope.",
    )
    # Behaviour
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.WARNING,
    )
    is_enabled = models.BooleanField(default=True)
    notify_admins = models.BooleanField(
        default=True,
        help_text="Create in-app Notification(s) for staff/admins when it fires.",
    )
    # Evaluation state (updated by the alert evaluation task)
    breach_count = models.PositiveIntegerField(default=0)
    last_metric_value = models.FloatField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_ai_alert_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rule_key"]

    def __str__(self) -> str:
        return f"{self.rule_key} [{self.metric} {self.operator} {self.threshold_value}]"


class AIAlert(models.Model):
    """A triggered AI alert instance with a full lifecycle.

    Lifecycle: ``triggered`` → ``acknowledged`` → ``resolved``, or
    ``suppressed``. Created by the alert evaluation task (or manual
    ``alerts/evaluate/`` endpoint). Every admin lifecycle action is audited.
    """

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        TRIGGERED = "triggered", "Triggered"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        SUPPRESSED = "suppressed", "Suppressed"

    alert_key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    rule = models.ForeignKey(
        AIAlertRule,
        on_delete=models.SET_NULL,
        related_name="alerts",
        null=True,
        blank=True,
    )
    alert_type = models.CharField(max_length=30, choices=AIAlertRule.AlertType.choices)
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.WARNING,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.TRIGGERED,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    # Metric context
    metric_name = models.CharField(max_length=40)
    metric_value = models.FloatField(default=0.0)
    threshold_value = models.FloatField(default=0.0)
    # Scope
    feature = models.ForeignKey(
        AIFeatureRegistry,
        on_delete=models.SET_NULL,
        related_name="ai_alerts",
        null=True,
        blank=True,
    )
    provider = models.CharField(max_length=100, blank=True, default="")
    model_name = models.CharField(max_length=200, blank=True, default="")
    # Anti-noise / traceability
    dedup_key = models.CharField(max_length=64, db_index=True, blank=True, default="")
    breach_count = models.PositiveIntegerField(default=1)
    # Lifecycle
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_ai_alerts",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_ai_alerts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)
    triggered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-triggered_at"]
        indexes = [
            models.Index(fields=["alert_type", "triggered_at"], name="ai_alert_type_time_idx"),
            models.Index(fields=["status", "triggered_at"], name="ai_alert_status_time_idx"),
            models.Index(fields=["severity", "status"], name="ai_alert_sev_status_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.title} ({self.status})"
