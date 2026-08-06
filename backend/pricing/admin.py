from django.contrib import admin

from .models import MarketStat


@admin.register(MarketStat)
class MarketStatAdmin(admin.ModelAdmin):
    """Read-only view onto a computed snapshot — rows only ever come from
    `python manage.py update_market_stats`, never a hand-filled admin form."""

    list_display = [
        "area",
        "room_type",
        "avg_price",
        "median_price",
        "sample_size",
        "calculated_at",
    ]
    list_filter = ["area", "room_type"]
    readonly_fields = [
        "area",
        "room_type",
        "avg_price",
        "median_price",
        "min_price",
        "max_price",
        "percentile_25",
        "percentile_75",
        "sample_size",
        "calculated_at",
    ]

    def has_add_permission(self, request):
        return False
