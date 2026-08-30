"""Property Intelligence API — public + staff endpoints (Phase 19.1).

- ``GET /api/v1/property-intelligence/<room_id>/`` — public read (same default
  permission as room detail), transparent breakdown + confidence + suggestions.
- ``GET /api/v1/property-intelligence/<room_id>/staff/`` — staff/admin detail
  with signal provenance, benchmarks and engine metadata; access is audited.

Public output never contains internal fraud risk scores, graph/ring IDs, KYC
data or model/provider details.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def _room_or_404(room_id: int):
    from rooms.models import Room

    try:
        return Room.objects.select_related("owner").prefetch_related("images").get(pk=room_id)
    except Room.DoesNotExist:
        return None


def _is_admin(user) -> bool:
    role = getattr(user, "role", "")
    return bool(
        getattr(user, "is_staff", False)
        or role == getattr(getattr(user, "Role", None), "ADMIN", "admin")
    )


_BREAKDOWN_COMPONENT = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "nullable": True},
        "weight": {"type": "number"},
        "effective_weight": {"type": "number"},
        "contribution": {"type": "number", "nullable": True},
        "availability": {"type": "string", "enum": ["available", "unavailable"]},
        "note": {"type": "string"},
    },
}

_PUBLIC_SCHEMA = {
    "type": "object",
    "properties": {
        "room_id": {"type": "integer"},
        "score": {"type": "integer", "nullable": True},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "none"]},
        "confidence_reasons": {"type": "array", "items": {"type": "string"}},
        "score_version": {"type": "string"},
        "computed_at": {"type": "string"},
        "breakdown": {
            "type": "object",
            "properties": {
                "listing_quality": _BREAKDOWN_COMPONENT,
                "price_value": _BREAKDOWN_COMPONENT,
                "location": _BREAKDOWN_COMPONENT,
                "photo_trust": _BREAKDOWN_COMPONENT,
                "trust": _BREAKDOWN_COMPONENT,
                "demand": _BREAKDOWN_COMPONENT,
            },
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "data_freshness": {"type": "object", "additionalProperties": True},
        "disclaimer": {"type": "string"},
    },
}

_STAFF_SCHEMA = {
    "allOf": [
        _PUBLIC_SCHEMA,
        {
            "type": "object",
            "properties": {
                "provenance": {"type": "object", "additionalProperties": True},
                "_engine": {"type": "object", "additionalProperties": True},
            },
        },
    ]
}


@extend_schema(
    tags=["Property Intelligence"],
    summary="Property Intelligence Score for one listing",
    description=(
        "Transparent, deterministic 0-100 composite of listing quality, price "
        "competitiveness, location/commute value, photo authenticity, trust "
        "and demand signals. Informational only — not a valuation, fraud "
        "verdict or guarantee of performance."
    ),
    parameters=[OpenApiParameter("room_id", int, OpenApiParameter.PATH)],
    responses={200: _PUBLIC_SCHEMA, 404: {"detail": "string"}},
)
class PropertyIntelligenceView(APIView):
    """Public detail — score, confidence, breakdown, suggestions."""

    def get(self, request, room_id: int):
        room = _room_or_404(room_id)
        if room is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from .engine import get_property_intelligence

        return Response(get_property_intelligence(room))


@extend_schema(
    tags=["Property Intelligence"],
    summary="Staff detail — signal provenance + calculation metadata",
    description=(
        "Staff/admin-only detail. Reuses the public payload and additionally "
        "returns market benchmarks, fraud-report severity + detector names, "
        "verification flags, photo/demand provenance and engine metadata. "
        "Raw NID/phone/device or graph data is never returned."
    ),
    parameters=[OpenApiParameter("room_id", int, OpenApiParameter.PATH)],
    responses={200: _STAFF_SCHEMA, 403: {"detail": "string"}, 404: {"detail": "string"}},
)
class PropertyIntelligenceStaffView(APIView):
    """Staff/admin detail — same compute, internal provenance attached."""

    permission_classes = [IsAuthenticated]

    def get(self, request, room_id: int):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        room = _room_or_404(room_id)
        if room is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from fraud.services.privacy import audit_log_access

        from .engine import get_property_intelligence

        audit_log_access(request.user, "property_intelligence", room_id, "staff_view")
        return Response(get_property_intelligence(room, include_internal=True))
