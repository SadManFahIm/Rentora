"""AI Intelligence admin configuration."""

from django.contrib import admin

from .models import AIExecutionLog, AIFeatureRegistry, AIPrompt, AIPromptVersion, ProviderHealth


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
