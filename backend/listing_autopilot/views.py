"""Listing Autopilot API views (Phase 19.3).

Landlord-facing, read-mostly surface for the autopilot:

* ``GET  /api/v1/autopilot/overview/``   — feature availability + pending counts.
* ``GET  /api/v1/autopilot/proposals/``  — the landlord's own proposals.
* ``POST /api/v1/autopilot/proposals/<key>/approve/`` — approve + apply (owner).
* ``POST /api/v1/autopilot/proposals/<key>/reject/``  — reject (owner).
* ``POST /api/v1/autopilot/proposals/bulk-approve/``  — approve many valid ones.

Every proposal endpoint references the requesting user's own rows, enforces
ownership server-side, and scopes rate-limiting. Reading is cheap; the only
state-changing path mirrors the SDK's locked apply.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.models import AgentProposal
from config.throttling import TrustedUserRateThrottle

from . import constants as C
from .serializers import RejectSerializer
from .services import (
    AutopilotError,
    ConsentError,
    autopilot_approve_and_apply,
    autopilot_reject,
    landlord_analyses,
    landlord_proposals,
    proposal_payload,
)


class AutopilotRateThrottle(TrustedUserRateThrottle):
    scope = "listing_autopilot"


def _get_own_proposal(request, proposal_key: str) -> AgentProposal:
    return get_object_or_404(
        AgentProposal.objects.select_related("run__conversation"),
        proposal_key=proposal_key,
        run__conversation__user=request.user,
        run__conversation__agent__key=C.AGENT_KEY,
    )


def _feature_enabled(user) -> bool:
    try:
        from ai_intelligence.services import is_feature_available

        return is_feature_available(C.FEATURE_ID, user=user)
    except Exception:
        # Feature registry may be unseeded in fresh environments — degrade
        # deterministically to disabled (never a partial truth).
        return False


class AutopilotOverviewView(APIView):
    """Landlord dashboard header: enabled status + pending proposal count."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AutopilotRateThrottle]

    def get(self, request):
        enabled = _feature_enabled(request.user)
        pending = landlord_proposals(request.user, status="pending", limit=500)
        return Response(
            {
                "enabled": enabled,
                "pending_count": len(pending),
                "agent": C.AGENT_KEY,
            }
        )


class AutopilotProposalsView(APIView):
    """Landlord's own autopilot proposals (pending by default)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AutopilotRateThrottle]

    @extend_schema(parameters=[OpenApiParameter("status", str, "query", required=False)])
    def get(self, request):
        raw = request.query_params.get("status", "")
        status_filter = (
            raw
            if raw in ("pending", "approved", "applied", "rejected", "expired", "failed", "")
            else "pending"
        )
        proposals = landlord_proposals(request.user, status=status_filter, limit=100)
        return Response({"proposals": [proposal_payload(p) for p in proposals]})


class AutopilotAnalysesView(APIView):
    """Landlord's listing analysis snapshots (weekly scores + grounding)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AutopilotRateThrottle]

    def get(self, request):
        analyses = landlord_analyses(request.user, limit=50)
        return Response(
            {
                "analyses": [
                    {
                        "id": a.pk,
                        "room_id": a.room_id,
                        "week_key": a.week_key,
                        "eligible": a.eligible,
                        "quality_score": a.quality_score,
                        "property_score": a.property_score,
                        "property_confidence": a.property_confidence,
                        "price_direction": a.price_direction,
                        "suggested_price": float(a.suggested_price) if a.suggested_price else None,
                        "stale_days": a.stale_days,
                        "summary": a.summary,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in analyses
                ]
            }
        )


class ProposalApproveView(APIView):
    """Landlord approves + applies their own autopilot proposal."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AutopilotRateThrottle]

    @extend_schema(parameters=[OpenApiParameter("proposal_key", str, "path")])
    def post(self, request, proposal_key):
        proposal = _get_own_proposal(request, proposal_key)
        try:
            applied = autopilot_approve_and_apply(request.user, proposal)
        except PermissionDenied:
            return Response({"error": "not_proposal_owner"}, status=status.HTTP_403_FORBIDDEN)
        except ConsentError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"proposal_key": str(applied.proposal_key), "status": applied.status})


class ProposalRejectView(APIView):
    """Landlord rejects their own autopilot proposal."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AutopilotRateThrottle]

    @extend_schema(parameters=[OpenApiParameter("proposal_key", str, "path")])
    def post(self, request, proposal_key):
        proposal = _get_own_proposal(request, proposal_key)
        ser = RejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            rejected = autopilot_reject(request.user, proposal, reason=ser.validated_data["reason"])
        except PermissionDenied:
            return Response({"error": "not_proposal_owner"}, status=status.HTTP_403_FORBIDDEN)
        except ConsentError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"proposal_key": str(rejected.proposal_key), "status": rejected.status})


class ProposalBulkApproveView(APIView):
    """Approve+apply every *valid* PENDING autopilot proposal the landlord
    selected. Invalid/expired/owned-by-other entries are skipped (reported)
    rather than failing the batch — one bad row must not abort the rest.
    Only listed proposal types are evaluated (defense in depth)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AutopilotRateThrottle]

    def post(self, request):
        keys = request.data.get("proposal_keys") or []
        if not isinstance(keys, list) or not keys:
            return Response({"error": "no_proposals"}, status=status.HTTP_400_BAD_REQUEST)
        keys = [str(k) for k in keys[:200]]
        own = {
            str(p.proposal_key): p
            for p in landlord_proposals(request.user, status="pending", limit=500)
        }
        applied, skipped = [], []
        for key in keys:
            proposal = own.get(key)
            if proposal is None:
                skipped.append({"key": key, "reason": "not_found"})
                continue
            try:
                result = autopilot_approve_and_apply(request.user, proposal)
                applied.append({"key": str(result.proposal_key), "status": result.status})
            except (ConsentError, AutopilotError, PermissionDenied) as exc:
                skipped.append({"key": key, "reason": str(exc)})
        return Response({"applied": applied, "skipped": skipped})
