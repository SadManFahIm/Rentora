"""Agent SDK Django admin — Phase 19.0."""

from django.contrib import admin

from .models import (
    Agent,
    AgentConversation,
    AgentMessage,
    AgentProposal,
    AgentRun,
    AgentToolCall,
)


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ["key", "name", "status", "audience", "permission", "provider", "model_name"]
    list_filter = ["status", "audience", "permission"]
    search_fields = ["key", "name", "description"]
    readonly_fields = ["version", "created_at", "updated_at"]


@admin.register(AgentConversation)
class AgentConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "agent", "user", "title", "status", "last_activity_at"]
    list_filter = ["status"]
    search_fields = ["title", "agent__key", "user__email"]
    readonly_fields = ["started_at", "last_activity_at"]


@admin.register(AgentMessage)
class AgentMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "role", "sequence", "timestamp"]
    list_filter = ["role"]
    search_fields = ["content"]
    readonly_fields = ["sequence", "timestamp"]


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = [
        "run_key",
        "conversation",
        "agent",
        "status",
        "provider",
        "model_name",
        "turn_count",
        "tool_call_count",
        "estimated_cost_usd",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["run_key", "agent__key", "termination_reason"]
    readonly_fields = [
        "run_key",
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
        "started_at",
        "completed_at",
        "metadata",
    ]


@admin.register(AgentToolCall)
class AgentToolCallAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "run",
        "tool_name",
        "execution_status",
        "permission_decision",
        "created_at",
    ]
    list_filter = ["execution_status", "permission_decision"]
    search_fields = ["tool_name"]
    readonly_fields = ["created_at"]


@admin.register(AgentProposal)
class AgentProposalAdmin(admin.ModelAdmin):
    list_display = [
        "proposal_key",
        "proposal_type",
        "run",
        "status",
        "approval_required",
        "created_at",
    ]
    list_filter = ["status", "approval_required"]
    search_fields = ["proposal_key", "proposal_type", "summary"]
    readonly_fields = [
        "proposal_key",
        "run",
        "tool_call",
        "created_at",
        "expires_at",
        "reviewed_at",
        "reviewed_by",
        "applied_at",
        "applied_by",
    ]

    def has_add_permission(self, request):
        return False
