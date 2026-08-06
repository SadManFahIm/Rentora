from django.contrib import admin

from .models import FraudReport, FraudSignal


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
