"""AI Intelligence Layer — Phase 18.1 API views.

All views require admin authentication (IsAdminUser).
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIExecutionLog, AIFeatureRegistry, ProviderHealth
from .serializers import (
    AIExecutionLogSerializer,
    AIFeatureRegistrySerializer,
    ProviderHealthSerializer,
    ProviderStatsSerializer,
)
from .services import get_provider_stats, update_provider_health


class AIFeatureRegistryListView(generics.ListAPIView):
    """List all registered AI features."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIFeatureRegistrySerializer
    queryset = AIFeatureRegistry.objects.all()


class AIFeatureRegistryDetailView(generics.RetrieveAPIView):
    """Retrieve a single AI feature by feature_id."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIFeatureRegistrySerializer
    queryset = AIFeatureRegistry.objects.all()
    lookup_field = "feature_id"


class AIExecutionLogListView(generics.ListAPIView):
    """List AI execution logs with optional filtering."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIExecutionLogSerializer

    def get_queryset(self):
        qs = AIExecutionLog.objects.select_related("user").all()

        # Filter by feature
        feature_key = self.request.query_params.get("feature_key")
        if feature_key:
            qs = qs.filter(feature_key=feature_key)

        # Filter by provider
        provider = self.request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider=provider)

        # Filter by status
        exec_status = self.request.query_params.get("status")
        if exec_status:
            qs = qs.filter(status=exec_status)

        # Filter by user
        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Filter by execution_id
        execution_id = self.request.query_params.get("execution_id")
        if execution_id:
            qs = qs.filter(execution_id=execution_id)

        # Limit results
        try:
            limit = min(int(self.request.query_params.get("limit", 100)), 500)
        except (ValueError, TypeError):
            limit = 100
        return qs[:limit]


class AIExecutionLogDetailView(generics.RetrieveAPIView):
    """Retrieve a single execution log by execution_id."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIExecutionLogSerializer
    queryset = AIExecutionLog.objects.all()
    lookup_field = "execution_id"


class ProviderHealthListView(generics.ListAPIView):
    """List provider health records with optional filtering."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProviderHealthSerializer

    def get_queryset(self):
        qs = ProviderHealth.objects.all()

        # Filter by provider
        provider = self.request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider=provider)

        # Filter by feature
        feature_key = self.request.query_params.get("feature_key")
        if feature_key:
            qs = qs.filter(feature_key=feature_key)

        # Filter by health status
        is_healthy = self.request.query_params.get("is_healthy")
        if is_healthy is not None:
            qs = qs.filter(is_healthy=is_healthy.lower() == "true")

        return qs


class ProviderStatsView(APIView):
    """Get aggregated provider statistics for a time window."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        feature_key = request.query_params.get("feature_key")
        provider = request.query_params.get("provider")
        try:
            hours = int(request.query_params.get("hours", 24))
        except (ValueError, TypeError):
            hours = 24

        stats = get_provider_stats(
            feature_id=feature_key,
            provider=provider,
            hours=hours,
        )
        serializer = ProviderStatsSerializer(stats)
        return Response(serializer.data)


class UpdateProviderHealthView(APIView):
    """Manually trigger provider health aggregation."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        try:
            hours = int(request.data.get("hours", 1))
        except (ValueError, TypeError):
            hours = 1
        updated = update_provider_health(hours=hours)
        return Response(
            {"updated": updated, "message": f"Updated {updated} provider health records."},
            status=status.HTTP_200_OK,
        )
