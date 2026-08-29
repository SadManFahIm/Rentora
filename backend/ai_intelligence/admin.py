"""AI Intelligence admin configuration."""

from django.contrib import admin

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


class AIPromptVersionInline(admin.TabularInline):
    model = AIPromptVersion
    extra = 0
    readonly_fields = [
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
    fields = readonly_fields
    ordering = ["-version"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AIFeatureRegistry)
class AIFeatureRegistryAdmin(admin.ModelAdmin):
    list_display = [
        "feature_id",
        "name",
        "category",
        "status",
        "is_enabled",
        "owner",
        "default_provider",
        "default_model",
        "feature_flag_key",
        "estimated_cost_per_request",
        "created_at",
    ]
    list_filter = ["category", "status", "is_enabled"]
    search_fields = ["feature_id", "name", "description", "owner"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("feature_id", "name", "description", "category")}),
        ("Status", {"fields": ("status", "is_enabled", "owner")}),
        (
            "Provider & Model",
            {
                "fields": (
                    "default_provider",
                    "default_model",
                    "available_providers",
                    "fallback_strategy",
                )
            },
        ),
        (
            "Configuration",
            {"fields": ("feature_flag_key", "settings_key", "estimated_cost_per_request")},
        ),
        ("Metadata", {"fields": ("metadata", "created_at", "updated_at")}),
    )


@admin.register(AIPrompt)
class AIPromptAdmin(admin.ModelAdmin):
    list_display = [
        "prompt_key",
        "name",
        "category",
        "template_type",
        "status",
        "_active_version",
        "feature",
        "created_at",
    ]
    list_filter = ["status", "category", "template_type"]
    search_fields = ["prompt_key", "name", "description"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [AIPromptVersionInline]

    def _active_version(self, obj):
        av = obj.active_version
        return f"v{av.version}" if av else "—"

    _active_version.short_description = "Active"


@admin.register(AIPromptVersion)
class AIPromptVersionAdmin(admin.ModelAdmin):
    list_display = [
        "prompt",
        "version",
        "status",
        "is_active",
        "model_requirement",
        "created_by",
        "created_at",
    ]
    list_filter = ["status", "is_active"]
    search_fields = ["prompt__prompt_key", "change_summary"]
    readonly_fields = [
        "prompt",
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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AIExecutionLog)
class AIExecutionLogAdmin(admin.ModelAdmin):
    list_display = [
        "execution_id",
        "feature_key",
        "provider",
        "prompt_key",
        "status",
        "latency_ms",
        "confidence",
        "created_at",
    ]
    list_filter = ["status", "feature_key", "provider"]
    search_fields = ["execution_id", "feature_key", "provider", "prompt_key"]
    readonly_fields = [
        "execution_id",
        "created_at",
    ]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProviderHealth)
class ProviderHealthAdmin(admin.ModelAdmin):
    list_display = [
        "provider",
        "feature_key",
        "success_rate",
        "avg_latency_ms",
        "total_requests",
        "is_healthy",
        "window_start",
    ]
    list_filter = ["is_healthy", "provider", "feature_key"]
    search_fields = ["provider", "feature_key"]
    readonly_fields = ["created_at"]
    date_hierarchy = "window_start"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Phase 18.3 — Evaluation Framework Admin
# ---------------------------------------------------------------------------


@admin.register(EvaluationMetric)
class EvaluationMetricAdmin(admin.ModelAdmin):
    list_display = [
        "metric_key",
        "name",
        "metric_type",
        "category",
        "is_higher_better",
        "default_threshold",
    ]
    list_filter = ["metric_type", "category"]
    search_fields = ["metric_key", "name"]
    readonly_fields = ["created_at"]


@admin.register(EvaluationDataset)
class EvaluationDatasetAdmin(admin.ModelAdmin):
    list_display = [
        "dataset_key",
        "name",
        "version",
        "status",
        "dataset_type",
        "sample_count",
        "feature",
        "created_at",
    ]
    list_filter = ["status", "dataset_type"]
    search_fields = ["dataset_key", "name"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(EvaluationCase)
class EvaluationCaseAdmin(admin.ModelAdmin):
    list_display = ["case_id", "dataset", "created_at"]
    list_filter = ["dataset"]
    search_fields = ["case_id"]
    readonly_fields = ["created_at"]


@admin.register(EvaluationThreshold)
class EvaluationThresholdAdmin(admin.ModelAdmin):
    list_display = [
        "feature",
        "metric",
        "threshold_min",
        "threshold_max",
    ]
    list_filter = ["feature", "metric"]
    readonly_fields = ["created_at", "updated_at"]


class EvaluationCaseResultInline(admin.TabularInline):
    model = EvaluationCaseResult
    extra = 0
    readonly_fields = [
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
        "created_at",
    ]
    fields = readonly_fields


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = [
        "run_key_short",
        "feature",
        "model_name",
        "provider",
        "dataset",
        "status",
        "score",
        "total_cases",
        "passed_cases",
        "failed_cases",
        "duration_ms",
        "total_cost_usd",
        "created_at",
    ]
    list_filter = ["status", "feature"]
    search_fields = ["run_key", "model_name", "provider"]
    readonly_fields = [
        "run_key",
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
        "created_at",
        "updated_at",
    ]
    date_hierarchy = "created_at"
    inlines = [EvaluationCaseResultInline]

    @admin.display(description="Run ID")
    def run_key_short(self, obj):
        return str(obj.run_key)[:8]

    def has_add_permission(self, request):
        return False


@admin.register(EvaluationCaseResult)
class EvaluationCaseResultAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "run_short",
        "case",
        "passed",
        "score",
        "latency_ms",
        "created_at",
    ]
    list_filter = ["passed"]
    readonly_fields = [
        "run",
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

    @admin.display(description="Run")
    def run_short(self, obj):
        return str(obj.run.run_key)[:8]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Phase 18.4 — AI Alerts
# ---------------------------------------------------------------------------


@admin.register(AIAlertRule)
class AIAlertRuleAdmin(admin.ModelAdmin):
    list_display = [
        "rule_key",
        "name",
        "alert_type",
        "metric",
        "operator",
        "threshold_value",
        "severity",
        "is_enabled",
        "breach_count",
        "last_metric_value",
        "last_checked_at",
    ]
    list_filter = ["alert_type", "metric", "severity", "is_enabled"]
    search_fields = ["rule_key", "name", "provider", "model_name"]
    readonly_fields = ["breach_count", "last_metric_value", "last_checked_at"]


@admin.register(AIAlert)
class AIAlertAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "title_short",
        "severity",
        "status",
        "alert_type",
        "metric_name",
        "metric_value",
        "feature_ref",
        "triggered_at",
    ]
    list_filter = ["severity", "status", "alert_type"]
    search_fields = ["title", "message", "provider", "model_name", "dedup_key"]
    readonly_fields = [
        "alert_key",
        "rule",
        "alert_type",
        "severity",
        "status",
        "title",
        "message",
        "metric_name",
        "metric_value",
        "threshold_value",
        "feature",
        "provider",
        "model_name",
        "dedup_key",
        "breach_count",
        "meta",
        "triggered_at",
    ]
    date_hierarchy = "triggered_at"

    @admin.display(description="Title")
    def title_short(self, obj):
        return obj.title[:80]

    @admin.display(description="Feature")
    def feature_ref(self, obj):
        return obj.feature.feature_id if obj.feature else "—"

    def has_add_permission(self, request):
        return False
