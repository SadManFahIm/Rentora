"""AI Intelligence Layer — Phase 18.1 serializers."""

from rest_framework import serializers

from .models import AIExecutionLog, AIFeatureRegistry, ProviderHealth


class AIFeatureRegistrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIFeatureRegistry
        fields = [
            "id",
            "feature_id",
            "name",
            "description",
            "category",
            "is_enabled",
            "default_provider",
            "available_providers",
            "settings_key",
            "estimated_cost_per_request",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AIExecutionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIExecutionLog
        fields = [
            "execution_id",
            "feature_key",
            "provider",
            "provider_version",
            "model_name",
            "model_version",
            "status",
            "failure_type",
            "error_message",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_usd",
            "confidence",
            "is_fallback",
            "fallback_chain",
            "primary_provider",
            "metadata",
            "created_at",
        ]
        read_only_fields = [
            "execution_id",
            "created_at",
        ]


class ProviderHealthSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderHealth
        fields = [
            "id",
            "provider",
            "feature_key",
            "total_requests",
            "successful_requests",
            "failed_requests",
            "timeout_requests",
            "avg_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "total_cost_usd",
            "total_input_tokens",
            "total_output_tokens",
            "success_rate",
            "is_healthy",
            "window_start",
            "window_end",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class ProviderStatsSerializer(serializers.Serializer):
    """Serializer for aggregated provider statistics."""

    total_requests = serializers.IntegerField()
    successful = serializers.IntegerField()
    failed = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_latency_ms = serializers.FloatField(allow_null=True)
    total_cost_usd = serializers.DecimalField(max_digits=12, decimal_places=6, allow_null=True)
    total_tokens = serializers.IntegerField(allow_null=True)
    by_provider = serializers.ListField(child=serializers.DictField())
