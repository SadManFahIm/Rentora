"""AI Intelligence Layer — Phase 18.1 + 18.2 + 18.3 serializers."""

from rest_framework import serializers

from .models import (
    AIAlert,
    AIAlertRule,
    AIExecutionLog,
    AIFeatureRegistry,
    AIPrompt,
    AIPromptVersion,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationMetric,
    EvaluationRun,
    EvaluationThreshold,
    ProviderHealth,
)


class AIPromptVersionSerializer(serializers.ModelSerializer):
    prompt_key = serializers.CharField(source="prompt.prompt_key", read_only=True)

    class Meta:
        model = AIPromptVersion
        fields = [
            "id",
            "prompt_key",
            "version",
            "template",
            "system_instructions",
            "variables",
            "model_requirement",
            "status",
            "is_active",
            "change_summary",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "version", "created_by", "created_at"]


class AIPromptListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for prompt list view (no version content)."""

    active_version = serializers.SerializerMethodField()
    latest_version = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = AIPrompt
        fields = [
            "id",
            "prompt_key",
            "name",
            "description",
            "category",
            "template_type",
            "status",
            "default_model",
            "feature",
            "active_version",
            "latest_version",
            "version_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_active_version(self, obj):
        av = obj.active_version
        return av.version if av else None

    def get_latest_version(self, obj):
        lv = obj.latest_version
        return lv.version if lv else None

    def get_version_count(self, obj):
        return obj.versions.count()


class AIPromptDetailSerializer(serializers.ModelSerializer):
    """Full serializer for prompt detail with nested versions."""

    versions = AIPromptVersionSerializer(many=True, read_only=True)
    active_version = serializers.SerializerMethodField()

    class Meta:
        model = AIPrompt
        fields = [
            "id",
            "prompt_key",
            "name",
            "description",
            "category",
            "template_type",
            "status",
            "default_model",
            "input_schema",
            "output_schema",
            "feature",
            "active_version",
            "versions",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def get_active_version(self, obj):
        av = obj.active_version
        return av.version if av else None


class AIPromptCreateSerializer(serializers.Serializer):
    """Serializer for creating a new prompt with first version."""

    prompt_key = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    category = serializers.ChoiceField(
        choices=AIFeatureRegistry.Category.choices,
        default="other",
    )
    feature = serializers.IntegerField(required=False, allow_null=True, default=None)
    template_type = serializers.ChoiceField(
        choices=AIPrompt.TemplateType.choices,
        default="template",
    )
    template = serializers.CharField()
    system_instructions = serializers.CharField(required=False, default="", allow_blank=True)
    default_model = serializers.CharField(required=False, default="", allow_blank=True)
    input_schema = serializers.DictField(required=False, default=dict)
    output_schema = serializers.DictField(required=False, default=dict)
    variables = serializers.DictField(required=False, default=dict)
    model_requirement = serializers.CharField(required=False, default="", allow_blank=True)
    change_summary = serializers.CharField(required=False, default="", allow_blank=True)


class AIPromptVersionCreateSerializer(serializers.Serializer):
    """Serializer for creating a new prompt version."""

    template = serializers.CharField()
    system_instructions = serializers.CharField(required=False, default="", allow_blank=True)
    variables = serializers.DictField(required=False, default=dict)
    model_requirement = serializers.CharField(required=False, default="", allow_blank=True)
    change_summary = serializers.CharField(required=False, default="", allow_blank=True)


class AIFeatureRegistrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIFeatureRegistry
        fields = [
            "id",
            "feature_id",
            "name",
            "description",
            "category",
            "status",
            "is_enabled",
            "owner",
            "default_provider",
            "default_model",
            "available_providers",
            "fallback_strategy",
            "feature_flag_key",
            "settings_key",
            "estimated_cost_per_request",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AIExecutionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIExecutionLog
        fields = [
            "execution_id",
            "feature_key",
            "provider",
            "provider_version",
            "model_name",
            "model_version",
            "prompt_key",
            "prompt_version",
            "status",
            "failure_type",
            "error_message",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_usd",
            "confidence",
            "is_fallback",
            "fallback_chain",
            "primary_provider",
            "metadata",
            "created_at",
        ]
        read_only_fields = [
            "execution_id",
            "created_at",
        ]


class ProviderHealthSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderHealth
        fields = [
            "id",
            "provider",
            "feature_key",
            "total_requests",
            "successful_requests",
            "failed_requests",
            "timeout_requests",
            "avg_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "total_cost_usd",
            "total_input_tokens",
            "total_output_tokens",
            "success_rate",
            "is_healthy",
            "window_start",
            "window_end",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class ProviderStatsSerializer(serializers.Serializer):
    """Serializer for aggregated provider statistics."""

    total_requests = serializers.IntegerField()
    successful = serializers.IntegerField()
    failed = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_latency_ms = serializers.FloatField(allow_null=True)
    total_cost_usd = serializers.DecimalField(max_digits=12, decimal_places=6, allow_null=True)
    total_tokens = serializers.IntegerField(allow_null=True)
    by_provider = serializers.ListField(child=serializers.DictField())


# ---------------------------------------------------------------------------
# Phase 18.3 — Evaluation Framework Serializers
# ---------------------------------------------------------------------------


class EvaluationMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationMetric
        fields = [
            "id",
            "metric_key",
            "name",
            "description",
            "metric_type",
            "category",
            "formula",
            "is_higher_better",
            "default_threshold",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class EvaluationCaseSerializer(serializers.ModelSerializer):
    dataset_key = serializers.CharField(source="dataset.dataset_key", read_only=True)

    class Meta:
        model = EvaluationCase
        fields = [
            "id",
            "dataset",
            "dataset_key",
            "case_id",
            "input",
            "expected_output",
            "expected_labels",
            "metadata",
            "evaluation_criteria",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class EvaluationDatasetListSerializer(serializers.ModelSerializer):
    feature_id = serializers.CharField(source="feature.feature_id", read_only=True, default="")

    class Meta:
        model = EvaluationDataset
        fields = [
            "id",
            "dataset_key",
            "name",
            "description",
            "feature",
            "feature_id",
            "dataset_type",
            "status",
            "version",
            "sample_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "sample_count"]


class EvaluationDatasetDetailSerializer(serializers.ModelSerializer):
    cases = EvaluationCaseSerializer(many=True, read_only=True)

    class Meta:
        model = EvaluationDataset
        fields = [
            "id",
            "dataset_key",
            "name",
            "description",
            "feature",
            "dataset_type",
            "status",
            "version",
            "sample_count",
            "cases",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "sample_count"]


class EvaluationDatasetCreateSerializer(serializers.Serializer):
    dataset_key = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, default="")
    feature_id = serializers.CharField(required=False, default=None, allow_null=True)
    dataset_type = serializers.ChoiceField(
        choices=EvaluationDataset.DatasetType.choices,
        default="synthetic",
    )


class EvaluationThresholdSerializer(serializers.ModelSerializer):
    feature_id = serializers.CharField(source="feature.feature_id", read_only=True)
    metric_key = serializers.CharField(source="metric.metric_key", read_only=True)
    metric_name = serializers.CharField(source="metric.name", read_only=True)

    class Meta:
        model = EvaluationThreshold
        fields = [
            "id",
            "feature",
            "feature_id",
            "metric",
            "metric_key",
            "metric_name",
            "threshold_min",
            "threshold_max",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class EvaluationCaseResultSerializer(serializers.ModelSerializer):
    run_key = serializers.UUIDField(source="run.run_key", read_only=True)

    class Meta:
        model = EvaluationCaseResult
        fields = [
            "id",
            "run",
            "run_key",
            "case",
            "input_data",
            "actual_output",
            "expected_output",
            "metric_results",
            "passed",
            "score",
            "confidence",
            "latency_ms",
            "error_message",
            "evaluator_version",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class EvaluationRunListSerializer(serializers.ModelSerializer):
    feature_id = serializers.CharField(source="feature.feature_id", read_only=True, default="")
    dataset_key = serializers.CharField(source="dataset.dataset_key", read_only=True, default="")
    pass_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = EvaluationRun
        fields = [
            "id",
            "run_key",
            "feature",
            "feature_id",
            "dataset",
            "dataset_key",
            "dataset_version",
            "model_name",
            "provider",
            "experiment_key",
            "variant_key",
            "status",
            "started_at",
            "completed_at",
            "duration_ms",
            "total_cases",
            "passed_cases",
            "failed_cases",
            "error_count",
            "score",
            "metric_scores",
            "total_cost_usd",
            "pass_rate",
            "created_by",
            "created_at",
        ]
        read_only_fields = [
            "run_key",
            "started_at",
            "completed_at",
            "duration_ms",
            "total_cases",
            "passed_cases",
            "failed_cases",
            "error_count",
            "score",
            "metric_scores",
            "total_cost_usd",
            "created_at",
        ]


class EvaluationRunDetailSerializer(serializers.ModelSerializer):
    feature_id = serializers.CharField(source="feature.feature_id", read_only=True, default="")
    case_results = EvaluationCaseResultSerializer(many=True, read_only=True)
    pass_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = EvaluationRun
        fields = [
            "id",
            "run_key",
            "feature",
            "feature_id",
            "dataset",
            "dataset_version",
            "prompt",
            "prompt_version",
            "model_name",
            "provider",
            "baseline_run",
            "experiment_key",
            "variant_key",
            "status",
            "started_at",
            "completed_at",
            "duration_ms",
            "total_cases",
            "passed_cases",
            "failed_cases",
            "error_count",
            "score",
            "metric_scores",
            "total_cost_usd",
            "max_cases",
            "timeout_seconds",
            "metadata",
            "case_results",
            "pass_rate",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "run_key",
            "started_at",
            "completed_at",
            "duration_ms",
            "total_cases",
            "passed_cases",
            "failed_cases",
            "error_count",
            "score",
            "metric_scores",
            "total_cost_usd",
            "created_at",
            "updated_at",
        ]


class EvaluationRunCreateSerializer(serializers.Serializer):
    feature_id = serializers.CharField(required=False, default=None, allow_null=True)
    dataset_key = serializers.CharField(required=False, default=None, allow_null=True)
    dataset_version = serializers.IntegerField(required=False, default=None, allow_null=True)
    prompt_key = serializers.CharField(required=False, default=None, allow_null=True)
    prompt_version = serializers.IntegerField(required=False, default=None, allow_null=True)
    model_name = serializers.CharField(required=False, default="")
    provider = serializers.CharField(required=False, default="")
    baseline_run_id = serializers.IntegerField(required=False, default=None, allow_null=True)
    experiment_key = serializers.CharField(required=False, default="")
    variant_key = serializers.CharField(required=False, default="")
    max_cases = serializers.IntegerField(required=False, default=1000)
    timeout_seconds = serializers.IntegerField(required=False, default=3600)


class ModelComparisonSerializer(serializers.Serializer):
    feature_id = serializers.CharField()
    model_a = serializers.CharField()
    model_b = serializers.CharField()
    dataset_key = serializers.CharField()


class PromptComparisonSerializer(serializers.Serializer):
    prompt_key = serializers.CharField()
    version_a = serializers.IntegerField()
    version_b = serializers.IntegerField()
    dataset_key = serializers.CharField()


class RegressionCheckSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()


class RunComparisonSerializer(serializers.Serializer):
    run_a_id = serializers.IntegerField()
    run_b_id = serializers.IntegerField()


# ---------------------------------------------------------------------------
# Phase 18.4 — AI Intelligence Alerts
# ---------------------------------------------------------------------------


class AIAlertRuleSerializer(serializers.ModelSerializer):
    """Alert rule CRUD serializer.

    Accepts ``feature_id`` (the string identifier, not the integer PK) as a
    write field and exposes read-only evaluation state (breach_count,
    last_metric_value, last_checked_at) plus display labels.
    """

    feature_id = serializers.SerializerMethodField()
    metric_display = serializers.CharField(source="get_metric_display", read_only=True)
    operator_display = serializers.CharField(source="get_operator_display", read_only=True)
    alert_type_display = serializers.CharField(source="get_alert_type_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = AIAlertRule
        fields = [
            "id",
            "rule_key",
            "name",
            "description",
            "alert_type",
            "metric",
            "operator",
            "threshold_value",
            "feature_id",
            "provider",
            "model_name",
            "duration_minutes",
            "consecutive_checks",
            "cooldown_minutes",
            "severity",
            "is_enabled",
            "notify_admins",
            "breach_count",
            "last_metric_value",
            "last_checked_at",
            "created_by",
            "created_at",
            "updated_at",
            "metric_display",
            "operator_display",
            "alert_type_display",
            "severity_display",
        ]
        read_only_fields = [
            "id",
            "breach_count",
            "last_metric_value",
            "last_checked_at",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_feature_id(self, obj):
        return obj.feature.feature_id if obj.feature else None

    def validate(self, attrs):
        raw_feature_id = self.initial_data.get("feature_id")
        if raw_feature_id:
            feature = AIFeatureRegistry.objects.filter(feature_id=raw_feature_id).first()
            if not feature:
                raise serializers.ValidationError({"feature_id": "Unknown feature"})
            attrs["feature"] = feature
        else:
            if not self.instance or ("feature_id" in self.initial_data and not raw_feature_id):
                attrs["feature"] = None
        return attrs


class AIAlertSerializer(serializers.ModelSerializer):
    """Alert output serializer (alerts are created by the rule evaluator)."""

    rule_key = serializers.SerializerMethodField()
    feature_id = serializers.SerializerMethodField()
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    alert_type_display = serializers.CharField(source="get_alert_type_display", read_only=True)
    acknowledged_by_username = serializers.SerializerMethodField()
    resolved_by_username = serializers.SerializerMethodField()

    class Meta:
        model = AIAlert
        fields = [
            "id",
            "alert_key",
            "rule",
            "rule_key",
            "alert_type",
            "alert_type_display",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "title",
            "message",
            "metric_name",
            "metric_value",
            "threshold_value",
            "feature",
            "feature_id",
            "provider",
            "model_name",
            "dedup_key",
            "breach_count",
            "acknowledged_by",
            "acknowledged_by_username",
            "acknowledged_at",
            "resolved_by",
            "resolved_by_username",
            "resolved_at",
            "resolution_note",
            "meta",
            "triggered_at",
        ]

    def get_rule_key(self, obj):
        return obj.rule.rule_key if obj.rule else None

    def get_feature_id(self, obj):
        return obj.feature.feature_id if obj.feature else None

    def get_acknowledged_by_username(self, obj):
        return obj.acknowledged_by.username if obj.acknowledged_by else None

    def get_resolved_by_username(self, obj):
        return obj.resolved_by.username if obj.resolved_by else None


class AlertLifecycleActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
