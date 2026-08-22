from django.contrib import admin

from .models import DriftMetric, ModelVersion, RetrainRequest


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "status", "training_date", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "version")


@admin.register(DriftMetric)
class DriftMetricAdmin(admin.ModelAdmin):
    list_display = (
        "model_version",
        "metric_name",
        "value",
        "threshold_breached",
        "window_start",
        "created_at",
    )
    list_filter = ("threshold_breached",)
    raw_id_fields = ("model_version",)


@admin.register(RetrainRequest)
class RetrainRequestAdmin(admin.ModelAdmin):
    list_display = ("model_version", "reason", "status", "triggered_by", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("model_version", "triggered_by")
