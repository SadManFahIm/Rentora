"""Rentora AI Rental Agent — API views (Phase 19.2).

Own-conversation surface for tenants: create a conversation with the
``ai.rental_agent`` agent / send a turn, list own conversations, read an
enriched conversation (transcript with grounded room cards, pending/applied
bookmark proposals, deterministic suggestions, latest run status), review the
latest run, and self-consent (approve/reject) on their own pending
``bookmark.create`` proposals.

Every endpoint is ``IsAuthenticated`` + scoped-rate-limited and references the
requesting user's own rows only.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.errors import AgentRegistryError
from agents.models import Agent, AgentConversation, AgentProposal, AgentRun
from agents.services import create_conversation, create_run
from agents.tasks import schedule_agent_run
from config.throttling import TrustedUserRateThrottle

from .serializers import ChatRequestSerializer, ConsentRequestSerializer
from .services import (
    ConsentError,
    RentalAgentError,
    conversation_payload,
    is_bookmark_proposal,
    self_consent_and_apply,
    self_reject,
)

AGENT_KEY = "ai.rental_agent"


class RentalAgentRateThrottle(TrustedUserRateThrottle):
    """Agent turns run the full LLM + tool loop — a dedicated, bounded scope
    (``DEFAULT_THROTTLE_RATES['rental_agent']``) keeps one user from flooding
    the worker while still allowing a substantial chat session."""

    scope = "rental_agent"


def _get_own_conversation(request, pk: int) -> AgentConversation:
    return get_object_or_404(
        AgentConversation.objects.select_related("agent"), pk=pk, user=request.user
    )


def _get_own_proposal(request, proposal_key: str) -> AgentProposal:
    return get_object_or_404(
        AgentProposal.objects.select_related("run__conversation"),
        proposal_key=proposal_key,
        run__conversation__user=request.user,
    )


class RentalChatView(APIView):
    """Start a conversation with the AI Rental Agent, or send a turn into an
    existing one. Pulls the conversation id from the ``X-Rentora-Conversation``
    header when provided, else the payload."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [RentalAgentRateThrottle]

    def _conversation_id(self, request) -> int | None:
        header = request.headers.get("X-Rentora-Conversation")
        if header and header.strip().isdigit():
            return int(header.strip())
        value = request.data.get("conversation_id")
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    @extend_schema(
        tags=["Rental Agent"],
        summary="Send a turn to the AI Rental Agent",
        parameters=[OpenApiParameter("X-Rentora-Conversation", str, "header", required=False)],
    )
    def post(self, request):
        ser = ChatRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conversation_id = self._conversation_id(request)

        if conversation_id is None:
            agent = Agent.objects.filter(key=AGENT_KEY, status="active").first()
            if agent is None:
                return Response(
                    {"error": "agent_not_available"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            try:
                conversation = create_conversation(agent, request.user, title="AI Rental Agent")
            except AgentRegistryError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            conversation = _get_own_conversation(request, conversation_id)

        try:
            run, _ = create_run(conversation, ser.validated_data["message"], actor=request.user)
        except AgentRegistryError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        task_meta = schedule_agent_run(run)
        run.refresh_from_db()
        return Response(
            {
                "conversation_id": conversation.pk,
                "run_key": str(run.run_key),
                "status": run.status,
                "task_id": task_meta.get("task_id", ""),
            },
            status=status.HTTP_201_CREATED,
        )


class ConversationListView(APIView):
    """Authenticated: the user's own rental-agent conversations (latest
    activity first)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [RentalAgentRateThrottle]

    def get(self, request):
        qs = (
            AgentConversation.objects.filter(user=request.user, agent__key=AGENT_KEY)
            .order_by("-last_activity_at")
            .values("id", "title", "status", "last_activity_at")
        )
        return Response(list(qs))


class ConversationDetailView(APIView):
    """Authenticated: enriched conversation — transcript with grounded room
    cards, pending/applied bookmark proposals, suggestions and latest run."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [RentalAgentRateThrottle]

    def get(self, request, pk):
        conversation = _get_own_conversation(request, pk)
        return Response(conversation_payload(conversation))


class RunStatusView(APIView):
    """Authenticated: one of the user's rental-agent runs."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [RentalAgentRateThrottle]

    @extend_schema(parameters=[OpenApiParameter("run_key", str, "path")])
    def get(self, request, run_key):
        run = get_object_or_404(AgentRun, run_key=run_key, conversation__user=request.user)
        return Response(
            {
                "run_key": str(run.run_key),
                "status": run.status,
                "termination_reason": run.termination_reason or "",
                "error_message": (run.error_message or "")[:400],
                "turn_count": run.turn_count,
                "tool_call_count": run.tool_call_count,
                "total_tokens": run.total_tokens,
                "estimated_cost_usd": float(run.estimated_cost_usd or 0),
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
        )


class ProposalConsentView(APIView):
    """Tenant self-consent — approve (unknown action) or reject a pending
    bookmark proposal owned by the caller.

    Approval routes through ``services.self_consent_and_apply`` which locks
    the proposal, verifies ownership + type server-side, marks it approved by
    the owner and applies it exactly once via the SDK's locked apply path.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [RentalAgentRateThrottle]
    decision = "approve"

    @extend_schema(
        parameters=[OpenApiParameter("proposal_key", str, "path")],
        summary="Approve a pending bookmark proposal (tenant consent)",
    )
    def post(self, request, proposal_key):
        proposal = _get_own_proposal(request, proposal_key)
        if not is_bookmark_proposal(proposal):
            return Response(
                {"error": "unsupported_proposal_type"}, status=status.HTTP_400_BAD_REQUEST
            )
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            applied = self_consent_and_apply(request.user, proposal)
        except PermissionDenied:
            return Response({"error": "not_proposal_owner"}, status=status.HTTP_403_FORBIDDEN)
        except (ConsentError, RentalAgentError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"proposal_key": str(applied.proposal_key), "status": applied.status})


class ProposalRejectView(ProposalConsentView):
    decision = "reject"

    @extend_schema(
        parameters=[OpenApiParameter("proposal_key", str, "path")],
        summary="Reject a pending bookmark proposal (tenant declines)",
    )
    def post(self, request, proposal_key):
        proposal = _get_own_proposal(request, proposal_key)
        if not is_bookmark_proposal(proposal):
            return Response(
                {"error": "unsupported_proposal_type"}, status=status.HTTP_400_BAD_REQUEST
            )
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            rejected = self_reject(request.user, proposal, reason=ser.validated_data["note"])
        except PermissionDenied:
            return Response({"error": "not_proposal_owner"}, status=status.HTTP_403_FORBIDDEN)
        except (ConsentError, RentalAgentError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"proposal_key": str(rejected.proposal_key), "status": rejected.status})
