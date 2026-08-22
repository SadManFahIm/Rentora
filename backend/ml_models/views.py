"""Views for the ml_models app (Phase 17 — Stage 7).

Provides admin-only endpoints for listing model versions, drift metrics,
and retrain requests, plus POST endpoints for recording drift metrics
and triggering retrain requests.
"""

from __future__ import annotations

from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DriftMetric, ModelVersion, RetrainRequest


class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelVersion
        fields = [
            "id",
            "name",
            "version",
            "description",
            "status",
            "training_date",
            "metrics",
            "artifacts_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DriftMetricSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model_version.name", read_only=True)
    model_version_str = serializers.CharField(source="model_version.version", read_only=True)

    class Meta:
        model = DriftMetric
        fields = [
            "id",
            "model_version",
            "model_name",
            "model_version_str",
            "metric_name",
            "value",
            "baseline_value",
            "threshold_min",
            "threshold_max",
            "threshold_breached",
            "window_start",
            "window_end",
            "sample_count",
            "created_at",
        ]
        read_only_fields = fields


class DriftMetricCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriftMetric
        fields = [
            "model_version",
            "metric_name",
            "value",
            "baseline_value",
            "threshold_min",
            "threshold_max",
            "window_start",
            "window_end",
            "sample_count",
        ]


class RetrainRequestSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model_version.name", read_only=True)

    class Meta:
        model = RetrainRequest
        fields = [
            "id",
            "model_version",
            "model_name",
            "reason",
            "status",
            "triggered_by",
            "notes",
            "created_at",
            "completed_at",
        ]
        read_only_fields = ["id", "status", "triggered_by", "created_at", "completed_at"]


class RetrainRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetrainRequest
        fields = ["model_version", "reason", "notes"]


def _admin_check(user) -> bool:
    return user.is_staff or getattr(user, "role", "") == "admin"


class ModelVersionListView(APIView):
    """Admin-only: list all tracked model versions."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _admin_check(request.user):
            return Response({"detail": "Admin access required."}, status=403)
        qs = ModelVersion.objects.all()
        return Response(ModelVersionSerializer(qs, many=True).data)


class DriftMetricListView(APIView):
    """Admin-only: list drift metrics (GET) or record a new one (POST)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _admin_check(request.user):
            return Response({"detail": "Admin access required."}, status=403)
        qs = DriftMetric.objects.select_related("model_version")
        model_id = request.query_params.get("model_version")
        if model_id:
            qs = qs.filter(model_version_id=model_id)
        breached = request.query_params.get("breached")
        if breached is not None:
            qs = qs.filter(threshold_breached=breached.lower() in ("true", "1"))
        return Response(DriftMetricSerializer(qs[:100], many=True).data)

    def post(self, request):
        if not _admin_check(request.user):
            return Response({"detail": "Admin access required."}, status=403)
        ser = DriftMetricCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        metric = ser.save()
        # Auto-check threshold breach
        breached = False
        if metric.threshold_min is not None and metric.value < metric.threshold_min:
            breached = True
        if metric.threshold_max is not None and metric.value > metric.threshold_max:
            breached = True
        if breached != metric.threshold_breached:
            metric.threshold_breached = breached
            metric.save(update_fields=["threshold_breached"])
        return Response(DriftMetricSerializer(metric).data, status=status.HTTP_201_CREATED)


class RetrainRequestListView(APIView):
    """Admin-only: list retrain requests (GET) or create one (POST)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _admin_check(request.user):
            return Response({"detail": "Admin access required."}, status=403)
        qs = RetrainRequest.objects.select_related("model_version", "triggered_by")
        return Response(RetrainRequestSerializer(qs[:50], many=True).data)

    def post(self, request):
        if not _admin_check(request.user):
            return Response({"detail": "Admin access required."}, status=403)
        ser = RetrainRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        retrain = ser.save(triggered_by=request.user)
        return Response(RetrainRequestSerializer(retrain).data, status=status.HTTP_201_CREATED)


class RunDriftCheckView(APIView):
    """Admin-only: manually trigger a full drift check (POST)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not _admin_check(request.user):
            return Response({"detail": "Admin access required."}, status=403)
        from fraud.services.model_monitor import check_all_drift

        result = check_all_drift()
        return Response(result)
