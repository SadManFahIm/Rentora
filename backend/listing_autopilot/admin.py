"""Listing Autopilot admin (Phase 19.3)."""

from django.contrib import admin

from .models import ListingAnalysis


@admin.register(ListingAnalysis)
class ListingAnalysisAdmin(admin.ModelAdmin):
    list_display = ("room", "week_key", "eligible", "quality_score", "property_score", "created_at")
    list_filter = ("eligible", "week_key")
    search_fields = ("room__title", "room__id", "week_key")
    readonly_fields = (
        "room",
        "week_key",
        "eligible",
        "eligibility_blocks",
        "quality_score",
        "quality_level",
        "property_score",
        "property_confidence",
        "price_direction",
        "suggested_price",
        "photo_count",
        "stale_days",
        "grounding_key",
        "payload",
        "summary",
        "created_at",
        "updated_at",
    )
