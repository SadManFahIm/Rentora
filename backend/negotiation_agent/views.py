"""AI Negotiation Agent — API views (Phase 19.4).

Participant-scoped surface: start/continue an agent chat (optionally bound to a
room's negotiation), read own conversations/negotiations with their enriched
payloads, self-consent on offer/boundary/send/accept/finalize proposals, and
the plain-user offer reject/withdraw + negotiation reject/cancel endpoints.

Every endpoint is ``IsAuthenticated`` + scoped-rate-limited and only ever
touches the requesting user's own rows (offer/negotiation keys are re-checked
server-side). Ownership is never trusted from the client.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
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

from . import constants as C
from . import services as S
from .serializers import ChatRequestSerializer, ConsentRequestSerializer
from .services import (
    NegotiationConsentError,
    NegotiationError,
    NegotiationNotFound,
    cancel_negotiation,
    get_or_create_negotiation,
    negotiation_payload,
    reject_negotiation,
    reject_offer,
    resolve_negotiation,
    resolve_own_offer,
    self_consent_approve,
    self_reject,
)

AGENT_KEY = C.AGENT_KEY


def _resolve_negotiation_or_404(negotiation_key: str, user):
    """Participants resolve; everyone else sees a clean 404 (no existence leak
    for non-participants — same posture as ``get_object_or_404``)."""
    try:
        return resolve_negotiation(negotiation_key, user)
    except NegotiationNotFound:
        raise Http404("negotiation_not_found") from None


def _resolve_own_offer_or_404(negotiation, offer_key: str) -> S.M.NegotiationOffer:
    try:
        return resolve_own_offer(negotiation, offer_key)
    except NegotiationNotFound:
        raise Http404("offer_not_found") from None


class NegotiationRateThrottle(TrustedUserRateThrottle):
    """Agent turns + reads run the full LLM/tool loop — a dedicated scope
    (``DEFAULT_THROTTLE_RATES['negotiation']``) bounds one user's flood while
    still allowing a full discussion session."""

    scope = "negotiation"


class NegotiationActionThrottle(TrustedUserRateThrottle):
    """Cheap participant actions (consent, reject, cancel) — bounded but more
    generous than the chat scope."""

    scope = "negotiation_action"


def _own_conversation(request, pk: int) -> AgentConversation:
    return get_object_or_404(
        AgentConversation.objects.select_related("agent"), pk=pk, user=request.user
    )


def _negotiation_for_conversation(conversation) -> S.M.Negotiation | None:
    from .models import Negotiation

    return (
        Negotiation.objects.filter(
            Q(tenant_conversation=conversation) | Q(landlord_conversation=conversation)
        )
        .select_related("room", "tenant", "landlord", "chat_room")
        .first()
    )


def _own_proposal(request, proposal_key: str) -> AgentProposal:
    return get_object_or_404(
        AgentProposal.objects.select_related("run__conversation", "run__conversation__agent"),
        proposal_key=proposal_key,
        run__conversation__user=request.user,
    )


class NegotiationChatView(APIView):
    """Start a negotiation-agent conversation (optionally bound to a room's
    negotiation) or send a turn into an existing one."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationRateThrottle]

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

    def _agent(self):
        return Agent.objects.filter(key=AGENT_KEY, status="active").first()

    def _bind_or_create(self, request, room_id: int | None):
        """Return a conversation for the negotiation agent chat.

        * With ``conversation_id``: reuse the caller's own conversation (whose
          negotiation — if any — stays bound).
        * Without: a ``room_id`` creates/joins the negotiation for the pair.
        """
        conversation_id = self._conversation_id(request)
        if conversation_id is not None:
            return _own_conversation(request, conversation_id)

        agent = self._agent()
        if agent is None:
            return None, "agent_not_available"

        from rooms.models import Room

        room = None
        if room_id is not None:
            room = Room.objects.filter(pk=room_id).first()
            if room is None:
                return None, "room_not_found"
        if room is None:
            return None, "room_required_to_start"

        user = request.user
        owner_pk = getattr(room.owner, "pk", None)
        if user.pk == owner_pk:
            # The landlord responds to a tenant-initiated negotiation for the
            # listing: attach to the latest open one. Creating a fresh
            # negotiation without a tenant makes no sense.
            from .models import Negotiation

            negotiation = (
                Negotiation.objects.filter(room=room, landlord=user, status__in=S.M.OPEN_STATES)
                .order_by("-updated_at")
                .first()
            )
            if negotiation is None:
                return None, "landlord_needs_existing_negotiation"
            conversation = create_conversation(
                agent,
                user,
                title=f"Negotiation — {room.title}",
                metadata={"negotiation_key": str(negotiation.negotiation_key)},
            )
            S.bind_conversation(negotiation, conversation, user)
            return conversation, None

        # Tenant (or any non-owner) initiates with the listing owner.
        from django.contrib.auth import get_user_model

        User = get_user_model()
        landlord = User.objects.filter(pk=owner_pk).first() if owner_pk is not None else None
        if landlord is None:
            return None, "listing_has_no_owner"
        negotiation, _created = get_or_create_negotiation(room=room, tenant=user, landlord=landlord)
        conversation = create_conversation(
            agent,
            user,
            title=f"Negotiation — {room.title}",
            metadata={"negotiation_key": str(negotiation.negotiation_key)},
        )
        S.bind_conversation(negotiation, conversation, user)
        return conversation, None

    @extend_schema(
        tags=["Negotiation Agent"],
        summary="Send a turn to the AI Negotiation Agent (optionally bound to a room)",
        parameters=[OpenApiParameter("X-Rentora-Conversation", str, "header", required=False)],
    )
    def post(self, request):
        ser = ChatRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # Gate BEFORE any side effects: chats must not create negotiations or
        # conversations while the feature is turned off.
        try:
            from ai_intelligence.services import is_feature_available

            if not is_feature_available(C.FEATURE_ID, user=request.user):
                return Response(
                    {"error": "feature_unavailable"}, status=status.HTTP_400_BAD_REQUEST
                )
        except Exception:
            return Response({"error": "feature_unavailable"}, status=status.HTTP_400_BAD_REQUEST)

        conversation, err = self._bind_or_create(request, ser.validated_data.get("room_id"))
        if err:
            if err == "agent_not_available":
                return Response({"error": err}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            if err == "room_required_to_start":
                return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

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


class NegotiationConversationListView(APIView):
    """The caller's own negotiation-agent conversations (latest first)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationRateThrottle]

    def get(self, request):
        qs = (
            AgentConversation.objects.filter(user=request.user, agent__key=AGENT_KEY)
            .order_by("-last_activity_at")
            .values("id", "title", "status", "last_activity_at")
        )
        return Response(list(qs))


class NegotiationConversationDetailView(APIView):
    """Enriched conversation + its bound negotiation (if any)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationRateThrottle]

    def get(self, request, pk):
        conversation = _own_conversation(request, pk)
        from rental_agent.services import conversation_payload

        payload = conversation_payload(conversation)
        negotiation = _negotiation_for_conversation(conversation)
        if negotiation is not None:
            payload["negotiation"] = negotiation_payload(negotiation, request.user)
        else:
            payload["negotiation"] = None
        return Response(payload)


class NegotiationRunStatusView(APIView):
    """One of the caller's negotiation-agent runs."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationRateThrottle]

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


class NegotiationListView(APIView):
    """The caller's negotiations as participant (latest first, light rows)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationActionThrottle]

    def get(self, request):
        from .models import Negotiation

        qs = (
            Negotiation.objects.filter(Q(tenant=request.user) | Q(landlord=request.user))
            .select_related("room", "tenant", "landlord")
            .order_by("-updated_at")[:50]
        )
        rows = []
        for negotiation in qs:
            last_offer = (
                negotiation.offers.order_by("-created_at")
                .values("amount", "status", "kind", "created_at")
                .first()
            )
            rows.append(
                {
                    "key": str(negotiation.negotiation_key),
                    "room_id": negotiation.room_id,
                    "room_title": negotiation.room.title,
                    "room_price": int(negotiation.room.price),
                    "status": negotiation.status,
                    "my_role": negotiation.role_of(request.user),
                    "peer_name": (
                        negotiation.counterparty(request.user).get_full_name()
                        or negotiation.counterparty(request.user).username
                    )
                    if negotiation.counterparty(request.user)
                    else "",
                    "updated_at": negotiation.updated_at.isoformat(),
                    "last_offer": last_offer,
                }
            )
        return Response(rows)


class NegotiationDetailView(APIView):
    """Full participant payload for one negotiation (offers + timeline)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationActionThrottle]

    @extend_schema(parameters=[OpenApiParameter("negotiation_key", str, "path")])
    def get(self, request, negotiation_key):
        negotiation = _resolve_negotiation_or_404(negotiation_key, request.user)
        return Response(negotiation_payload(negotiation, request.user))


class ProposalConsentView(APIView):
    """Participant self-consent — approve (or reject) a pending negotiation
    proposal owned by the caller's conversation. Approval routes through
    ``services.self_consent_approve`` which locks, re-verifies ownership +
    participant role + proposal type and applies exactly once."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationActionThrottle]
    decision = "approve"

    @extend_schema(
        parameters=[OpenApiParameter("proposal_key", str, "path")],
        summary="Approve a pending negotiation proposal (participant consent)",
    )
    def post(self, request, proposal_key):
        proposal = _own_proposal(request, proposal_key)
        tool_name = (proposal.action or {}).get("tool", "")
        if tool_name not in C.NEGOTIATION_TOOLS:
            return Response(
                {"error": "unsupported_proposal_type"}, status=status.HTTP_400_BAD_REQUEST
            )
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            applied = self_consent_approve(request.user, proposal)
        except PermissionDenied:
            return Response({"error": "not_proposal_owner"}, status=status.HTTP_403_FORBIDDEN)
        except (NegotiationConsentError, NegotiationError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"proposal_key": str(applied.proposal_key), "status": applied.status})


class ProposalRejectView(ProposalConsentView):
    decision = "reject"

    @extend_schema(
        parameters=[OpenApiParameter("proposal_key", str, "path")],
        summary="Reject a pending negotiation proposal (participant declines)",
    )
    def post(self, request, proposal_key):
        proposal = _own_proposal(request, proposal_key)
        tool_name = (proposal.action or {}).get("tool", "")
        if tool_name not in C.NEGOTIATION_TOOLS:
            return Response(
                {"error": "unsupported_proposal_type"}, status=status.HTTP_400_BAD_REQUEST
            )
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            rejected = self_reject(request.user, proposal, reason=ser.validated_data["note"])
        except PermissionDenied:
            return Response({"error": "not_proposal_owner"}, status=status.HTTP_403_FORBIDDEN)
        except NegotiationConsentError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"proposal_key": str(rejected.proposal_key), "status": rejected.status})


class OfferRejectView(APIView):
    """Counterparty rejects an outstanding SENT offer; its sender withdraws it."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationActionThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("negotiation_key", str, "path"),
            OpenApiParameter("offer_key", str, "path"),
        ],
        summary="Reject (counterparty) or withdraw (sender) an outstanding offer",
    )
    def post(self, request, negotiation_key, offer_key):
        negotiation = _resolve_negotiation_or_404(negotiation_key, request.user)
        offer = _resolve_own_offer_or_404(negotiation, offer_key)
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = reject_offer(
                negotiation, request.user, offer, reason=ser.validated_data["note"]
            )
        except PermissionDenied:
            return Response({"error": "not_participant"}, status=status.HTTP_403_FORBIDDEN)
        except NegotiationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)


class NegotiationRejectView(APIView):
    """A participant rejects the whole negotiation (terminal REJECTED)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationActionThrottle]

    @extend_schema(
        parameters=[OpenApiParameter("negotiation_key", str, "path")],
        summary="Reject the whole negotiation as a participant",
    )
    def post(self, request, negotiation_key):
        negotiation = _resolve_negotiation_or_404(negotiation_key, request.user)
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = reject_negotiation(
                negotiation, request.user, reason=ser.validated_data["note"]
            )
        except PermissionDenied:
            return Response({"error": "not_participant"}, status=status.HTTP_403_FORBIDDEN)
        except NegotiationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)


class NegotiationCancelView(APIView):
    """A participant cancels the whole negotiation (terminal CANCELLED)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [NegotiationActionThrottle]

    @extend_schema(
        parameters=[OpenApiParameter("negotiation_key", str, "path")],
        summary="Cancel the whole negotiation as a participant",
    )
    def post(self, request, negotiation_key):
        negotiation = _resolve_negotiation_or_404(negotiation_key, request.user)
        ser = ConsentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = cancel_negotiation(
                negotiation, request.user, reason=ser.validated_data["note"]
            )
        except PermissionDenied:
            return Response({"error": "not_participant"}, status=status.HTTP_403_FORBIDDEN)
        except NegotiationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)
