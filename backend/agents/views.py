"""Agent SDK API views — Phase 19.0.

Public surface is deliberately minimal (catalog + own conversations +
runs + messages); everything review/ops related lives behind the admin
RBAC gate (``is_admin_user``) with an explicit proposal workflow.
"""

from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.trust_utils import is_admin_user

from . import services
from .errors import AgentRegistryError, ProposalError
from .models import (
    Agent,
    AgentConversation,
    AgentProposal,
    AgentRun,
    AgentToolCall,
)
from .serializers import (
    AgentConversationSerializer,
    AgentMessageSerializer,
    AgentProposalSerializer,
    AgentRunSerializer,
    AgentSerializer,
    AgentToolCallSerializer,
    ProposalReviewSerializer,
    PublicAgentSerializer,
    SendMessageSerializer,
    StartConversationSerializer,
)
from .tasks import schedule_agent_run


class AdminOrReadPermission:
    """Enforce admin/staff RBAC (config.trust_utils.is_admin_user)."""

    def has_permission(self, request, view):
        return is_admin_user(getattr(request, "user", None))


class IsAdmin(AdminOrReadPermission):
    pass


class AdminAPIView(APIView):
    """Base view gated by the admin/staff permission (is_admin_user)."""

    permission_classes = [AdminOrReadPermission]


# ---------------------------------------------------------------------------
# Admin — agent registry
# ---------------------------------------------------------------------------


class AgentRegistryListView(AdminAPIView):
    """Admin: list all agents (any status) and register new ones."""

    def get(self, request):
        agents = services.list_agents(status=request.query_params.get("status", ""))
        return Response(AgentSerializer(agents, many=True).data)

    def post(self, request):
        data = request.data
        key = data.get("key")
        name = data.get("name")
        if not key or not name:
            return Response(
                {"error": "key and name are required"}, status=status.HTTP_400_BAD_REQUEST
            )
        agent = services.register_agent(
            key=key,
            name=name,
            description=data.get("description", ""),
            status=data.get("status", "disabled"),
            audience=data.get("audience", "staff"),
            permission=data.get("permission", "operator"),
            feature_id=data.get("feature_id", ""),
            prompt_key=data.get("prompt_key", ""),
            provider=data.get("provider", ""),
            model_name=data.get("model_name", ""),
            system_instructions=data.get("system_instructions", ""),
            enabled_tools=data.get("enabled_tools") or None,
            max_turns=data.get("max_turns") or None,
            max_tool_calls=data.get("max_tool_calls") or None,
            max_tokens=data.get("max_tokens") or None,
            max_cost_usd=data.get("max_cost_usd") or None,
            timeout_seconds=data.get("timeout_seconds") or None,
            metadata=data.get("metadata") or None,
        )
        return Response(AgentSerializer(agent).data, status=status.HTTP_201_CREATED)


class AgentRegistryDetailView(AdminAPIView):
    """Admin: retrieve/patch (update) an agent definition."""

    def get_agent(self, key):
        return get_object_or_404(Agent, key=key)

    def get(self, request, key):
        return Response(AgentSerializer(self.get_agent(key)).data)

    def patch(self, request, key):
        agent = self.get_agent(key)
        fields = [
            "name",
            "description",
            "status",
            "audience",
            "permission",
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
        ]
        for field in fields:
            if field in request.data:
                setattr(agent, field, request.data[field])
        if request.data.get("feature_id"):
            from ai_intelligence.models import AIFeatureRegistry

            agent.feature = AIFeatureRegistry.objects.filter(
                feature_id=request.data["feature_id"]
            ).first()
        agent.version = (agent.version or 1) + 1
        agent.save()
        return Response(AgentSerializer(agent).data)

    def delete(self, request, key):
        agent = self.get_agent(key)
        agent.status = "disabled"
        agent.save()
        return Response({"ok": True, "status": agent.status})


class AgentActivateView(AdminAPIView):
    def post(self, request, key):
        agent = get_object_or_404(Agent, key=key)
        agent.status = "active"
        agent.save()
        return Response(AgentSerializer(agent).data)


class AgentDeactivateView(AdminAPIView):
    def post(self, request, key):
        agent = get_object_or_404(Agent, key=key)
        agent.status = "disabled"
        agent.save()
        return Response(AgentSerializer(agent).data)


# ---------------------------------------------------------------------------
# Public / authenticated — catalog + conversations
# ---------------------------------------------------------------------------


class AgentCatalogView(APIView):
    """List invocable agents the caller may use (audience-aware)."""

    permission_classes = [AllowAny]

    def get(self, request):
        agents = Agent.objects.filter(status="active")
        if not is_admin_user(request.user):
            if not (request.user and request.user.is_authenticated):
                agents = agents.filter(audience="public")
            else:
                agents = agents.exclude(audience="staff")
        return Response(PublicAgentSerializer(agents, many=True).data)


class AgentCatalogDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, key):
        agent = get_object_or_404(Agent, key=key, status="active")
        if agent.audience == "staff" and not is_admin_user(request.user):
            return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PublicAgentSerializer(agent).data)


class ConversationListCreateView(APIView):
    """Authenticated: list own conversations, or start a new one with an
    active agent."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            AgentConversation.objects.filter(user=request.user)
            .annotate(message_count=Count("messages"))
            .order_by("-last_activity_at")
        )
        return Response(AgentConversationSerializer(qs, many=True).data)

    def post(self, request):
        ser = StartConversationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        agent = Agent.objects.filter(key=ser.validated_data["agent_key"]).first()
        if agent is None or agent.status != "active":
            return Response(
                {"error": "agent_not_found_or_inactive"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            conversation = services.create_conversation(
                agent, request.user, title=ser.validated_data.get("title", "")
            )
        except AgentRegistryError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            AgentConversationSerializer(conversation).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        return get_object_or_404(AgentConversation, pk=pk, user=request.user)

    def get(self, request, pk):
        return Response(AgentConversationSerializer(self.get_object(request, pk)).data)


class ConversationMessagesView(APIView):
    """Own conversation transcript + send a new message (starts a run)."""

    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        return get_object_or_404(
            AgentConversation.objects.prefetch_related("messages"),
            pk=pk,
            user=request.user,
        )

    def get(self, request, pk):
        conversation = self.get_object(request, pk)
        ser = AgentMessageSerializer(conversation.messages.all(), many=True)
        return Response(ser.data)

    def post(self, request, pk):
        conversation = self.get_object(request, pk)
        ser = SendMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            run, _ = services.create_run(
                conversation,
                ser.validated_data["message"],
                actor=request.user,
            )
        except AgentRegistryError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        task_meta = schedule_agent_run(run)
        run.refresh_from_db()
        return Response(
            {
                "run_key": str(run.run_key),
                "status": run.status,
                "task_id": task_meta.get("task_id", ""),
            },
            status=status.HTTP_201_CREATED,
        )


class ConversationRunsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conversation = get_object_or_404(AgentConversation, pk=pk, user=request.user)
        runs = AgentRun.objects.filter(conversation=conversation).order_by("-created_at")
        return Response(AgentRunSerializer(runs, many=True).data)


# ---------------------------------------------------------------------------
# Admin — runs, tool calls, proposals
# ---------------------------------------------------------------------------


class AgentRunListView(AdminAPIView):
    def get(self, request):
        qs = AgentRun.objects.select_related("agent").order_by("-created_at")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("conversation_id"):
            qs = qs.filter(conversation_id=request.query_params["conversation_id"])
        if request.query_params.get("agent_key"):
            qs = qs.filter(agent__key=request.query_params["agent_key"])
        return Response(AgentRunSerializer(qs[:200], many=True).data)


class AgentRunDetailView(AdminAPIView):
    def get(self, request, run_key):
        run = get_object_or_404(AgentRun, run_key=run_key)
        data = AgentRunSerializer(run).data
        data["tool_calls"] = AgentToolCallSerializer(run.tool_calls.all(), many=True).data
        return Response(data)


class AgentRunEvaluateView(AdminAPIView):
    """Evaluation hook: snapshot this run into the Phase 18.3 eval layer."""

    def post(self, request, run_key):
        run = get_object_or_404(AgentRun, run_key=run_key)
        try:
            eval_run = services.create_agent_eval_run(
                run.pk,
                feature_id=request.data.get("feature_id", ""),
                metric_keys=request.data.get("metric_keys") or None,
            )
        except AgentRegistryError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"eval_run_key": str(eval_run.run_key), "status": eval_run.status},
            status=status.HTTP_201_CREATED,
        )


class AgentToolCallListView(AdminAPIView):
    def get(self, request):
        qs = AgentToolCall.objects.select_related("run").order_by("-started_at")
        if request.query_params.get("run_id"):
            qs = qs.filter(run_id=request.query_params["run_id"])
        if request.query_params.get("tool_name"):
            qs = qs.filter(tool_name=request.query_params["tool_name"])
        return Response(AgentToolCallSerializer(qs[:200], many=True).data)


class ProposalListView(AdminAPIView):
    def get(self, request):
        qs = AgentProposal.objects.select_related("run", "run__agent").order_by("-created_at")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("agent_key"):
            qs = qs.filter(run__agent__key=request.query_params["agent_key"])
        data = AgentProposalSerializer(qs[:200], many=True).data
        # Bucket counts for a review queue.
        from django.db.models import Count

        counts = dict(
            AgentProposal.objects.values_list("status")
            .annotate(n=Count("id"))
            .values_list("status", "n")
        )
        return Response({"counts": counts, "results": data})


class ProposalDetailView(AdminAPIView):
    def get(self, request, proposal_key):
        proposal = get_object_or_404(AgentProposal, proposal_key=proposal_key)
        return Response(AgentProposalSerializer(proposal).data)


class ProposalApproveView(AdminAPIView):
    def post(self, request, proposal_key):
        proposal = get_object_or_404(AgentProposal, proposal_key=proposal_key)
        ser = ProposalReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            services.approve_proposal(
                proposal, request.user, note=ser.validated_data.get("note", "")
            )
        except ProposalError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AgentProposalSerializer(proposal).data)


class ProposalRejectView(AdminAPIView):
    def post(self, request, proposal_key):
        proposal = get_object_or_404(AgentProposal, proposal_key=proposal_key)
        ser = ProposalReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            services.reject_proposal(
                proposal, request.user, reason=ser.validated_data.get("reason", "")
            )
        except ProposalError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AgentProposalSerializer(proposal).data)


class ProposalApplyView(AdminAPIView):
    def post(self, request, proposal_key):
        proposal = get_object_or_404(AgentProposal, proposal_key=proposal_key)
        try:
            services.apply_proposal(proposal, actor=request.user)
        except ProposalError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AgentProposalSerializer(proposal).data)
