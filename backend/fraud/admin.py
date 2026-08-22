from django.contrib import admin

from .models import FraudReport, FraudSignal, GraphEdge, GraphNode


class FraudSignalInline(admin.TabularInline):
    """Inline editor for a report's detector findings."""

    model = FraudSignal
    extra = 0
    readonly_fields = ["detector", "severity", "message", "detail"]


@admin.register(FraudReport)
class FraudReportAdmin(admin.ModelAdmin):
    list_display = ["room", "severity", "score", "status", "updated_at"]
    list_filter = ["severity", "status"]
    search_fields = ["room__title", "room__owner__username"]
    readonly_fields = ["room", "severity", "score", "summary", "created_at", "updated_at"]
    inlines = [FraudSignalInline]


@admin.register(GraphNode)
class GraphNodeAdmin(admin.ModelAdmin):
    list_display = ["entity_type", "entity_id", "label", "risk_score", "community_id", "last_seen"]
    list_filter = ["entity_type", "community_id"]
    search_fields = ["entity_id", "label"]
    readonly_fields = ["first_seen", "last_seen"]
    ordering = ["-risk_score"]


@admin.register(GraphEdge)
class GraphEdgeAdmin(admin.ModelAdmin):
    list_display = ["source", "target", "edge_type", "strength", "weight", "last_seen"]
    list_filter = ["edge_type", "strength"]
    readonly_fields = ["first_seen", "last_seen"]
    ordering = ["-weight"]
