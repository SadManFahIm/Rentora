"""AI Intelligence admin configuration."""

from django.contrib import admin

from .models import AIExecutionLog, AIFeatureRegistry, ProviderHealth


@admin.register(AIFeatureRegistry)
class AIFeatureRegistryAdmin(admin.ModelAdmin):
    list_display = [
        "feature_id",
        "name",
        "category",
        "is_enabled",
        "default_provider",
        "estimated_cost_per_request",
        "created_at",
    ]
    list_filter = ["category", "is_enabled"]
    search_fields = ["feature_id", "name", "description"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(AIExecutionLog)
class AIExecutionLogAdmin(admin.ModelAdmin):
    list_display = [
        "execution_id",
        "feature_key",
        "provider",
        "status",
        "latency_ms",
        "confidence",
        "created_at",
    ]
    list_filter = ["status", "feature_key", "provider"]
    search_fields = ["execution_id", "feature_key", "provider"]
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
