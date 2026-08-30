"""Agent SDK API serializers — Phase 19.0."""

from rest_framework import serializers

from .models import (
    Agent,
    AgentConversation,
    AgentMessage,
    AgentProposal,
    AgentRun,
    AgentToolCall,
)


class PublicAgentSerializer(serializers.ModelSerializer):
    """Catalog-safe agent representation (no secrets, no internals)."""

    feature_id = serializers.CharField(source="feature.feature_id", read_only=True)

    class Meta:
        model = Agent
        fields = [
            "key",
            "name",
            "description",
            "status",
            "audience",
            "permission",
            "model_name",
            "feature_id",
            "created_at",
        ]
        read_only_fields = fields


class AgentSerializer(serializers.ModelSerializer):
    """Full admin serializer for the agent registry."""

    feature_id = serializers.CharField(source="feature.feature_id", read_only=True)
    is_invocable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Agent
        fields = [
            "key",
            "name",
            "description",
            "status",
            "audience",
            "permission",
            "version",
            "feature_id",
            "prompt_key",
            "provider",
            "model_name",
            "system_instructions",
            "enabled_tools",
            "max_turns",
            "max_tool_calls",
            "max_tokens",
            "max_cost_usd",
            "timeout_seconds",
            "metadata",
            "is_invocable",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["key", "is_invocable", "created_at", "updated_at"]


class AgentConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AgentConversation
        fields = [
            "id",
            "agent",
            "title",
            "status",
            "message_count",
            "started_at",
            "last_activity_at",
        ]
        read_only_fields = ["id", "started_at", "last_activity_at"]


class AgentMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMessage
        fields = ["id", "role", "content", "sequence", "timestamp"]
        read_only_fields = fields


class AgentRunSerializer(serializers.ModelSerializer):
    agent = serializers.CharField(source="agent.key", read_only=True)

    class Meta:
        model = AgentRun
        fields = [
            "run_key",
            "agent",
            "status",
            "provider",
            "model_name",
            "prompt_key",
            "prompt_version",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_usd",
            "turn_count",
            "tool_call_count",
            "termination_reason",
            "error_message",
            "duration_ms",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class AgentToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentToolCall
        fields = [
            "id",
            "tool_name",
            "arguments",
            "execution_status",
            "permission_decision",
            "result",
            "error_message",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class AgentProposalSerializer(serializers.ModelSerializer):
    run = serializers.UUIDField(source="run.run_key", read_only=True)
    agent = serializers.CharField(source="run.agent.key", read_only=True)
    tool_name = serializers.CharField(source="proposal_type", read_only=True)

    class Meta:
        model = AgentProposal
        fields = [
            "proposal_key",
            "run",
            "agent",
            "tool_name",
            "title",
            "summary",
            "action",
            "status",
            "approval_required",
            "created_at",
            "expires_at",
            "reviewed_at",
            "reviewed_by",
            "rejection_reason",
            "applied_at",
            "applied_by",
            "application_result",
        ]
        read_only_fields = fields

    reviewed_by = serializers.SerializerMethodField()
    applied_by = serializers.SerializerMethodField()

    def get_reviewed_by(self, obj):
        return obj.reviewed_by_id

    def get_applied_by(self, obj):
        return obj.applied_by_id


class ProposalReviewSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class SendMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=8000, required=True)


class StartConversationSerializer(serializers.Serializer):
    agent_key = serializers.CharField(max_length=100, required=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
