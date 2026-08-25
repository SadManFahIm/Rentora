"""AI Intelligence Layer — Phase 18.1 + 18.2 serializers."""

from rest_framework import serializers

from .models import AIExecutionLog, AIFeatureRegistry, AIPrompt, AIPromptVersion, ProviderHealth


class AIPromptVersionSerializer(serializers.ModelSerializer):
    prompt_key = serializers.CharField(source="prompt.prompt_key", read_only=True)

    class Meta:
        model = AIPromptVersion
        fields = [
            "id",
            "prompt_key",
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
        read_only_fields = ["id", "version", "created_by", "created_at"]


class AIPromptListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for prompt list view (no version content)."""

    active_version = serializers.SerializerMethodField()
    latest_version = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = AIPrompt
        fields = [
            "id",
            "prompt_key",
            "name",
            "description",
            "category",
            "template_type",
            "status",
            "default_model",
            "feature",
            "active_version",
            "latest_version",
            "version_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_active_version(self, obj):
        av = obj.active_version
        return av.version if av else None

    def get_latest_version(self, obj):
        lv = obj.latest_version
        return lv.version if lv else None

    def get_version_count(self, obj):
        return obj.versions.count()


class AIPromptDetailSerializer(serializers.ModelSerializer):
    """Full serializer for prompt detail with nested versions."""

    versions = AIPromptVersionSerializer(many=True, read_only=True)
    active_version = serializers.SerializerMethodField()

    class Meta:
        model = AIPrompt
        fields = [
            "id",
            "prompt_key",
            "name",
            "description",
            "category",
            "template_type",
            "status",
            "default_model",
            "input_schema",
            "output_schema",
            "feature",
            "active_version",
            "versions",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def get_active_version(self, obj):
        av = obj.active_version
        return av.version if av else None


class AIPromptCreateSerializer(serializers.Serializer):
    """Serializer for creating a new prompt with first version."""

    prompt_key = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    category = serializers.ChoiceField(
        choices=AIFeatureRegistry.Category.choices,
        default="other",
    )
    feature = serializers.IntegerField(required=False, allow_null=True, default=None)
    template_type = serializers.ChoiceField(
        choices=AIPrompt.TemplateType.choices,
        default="template",
    )
    template = serializers.CharField()
    system_instructions = serializers.CharField(required=False, default="", allow_blank=True)
    default_model = serializers.CharField(required=False, default="", allow_blank=True)
    input_schema = serializers.DictField(required=False, default=dict)
    output_schema = serializers.DictField(required=False, default=dict)
    variables = serializers.DictField(required=False, default=dict)
    model_requirement = serializers.CharField(required=False, default="", allow_blank=True)
    change_summary = serializers.CharField(required=False, default="", allow_blank=True)


class AIPromptVersionCreateSerializer(serializers.Serializer):
    """Serializer for creating a new prompt version."""

    template = serializers.CharField()
    system_instructions = serializers.CharField(required=False, default="", allow_blank=True)
    variables = serializers.DictField(required=False, default=dict)
    model_requirement = serializers.CharField(required=False, default="", allow_blank=True)
    change_summary = serializers.CharField(required=False, default="", allow_blank=True)


class AIFeatureRegistrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIFeatureRegistry
        fields = [
            "id",
            "feature_id",
            "name",
            "description",
            "category",
            "status",
            "is_enabled",
            "owner",
            "default_provider",
            "default_model",
            "available_providers",
            "fallback_strategy",
            "feature_flag_key",
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
            "prompt_key",
            "prompt_version",
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
