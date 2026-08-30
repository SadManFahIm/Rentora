"""Property Intelligence Agent SDK tool — Phase 19.1.

``property.intelligence`` is a READ_ONLY tool registered through the Phase
19.0 ``AgentToolRegistry``. The executor is authoritative for the score: it
returns the exact output of :func:`property_intelligence.engine.
get_property_intelligence`, cached the same way as the public API. The agent
can never invent scores, change the listing, or relabel the result as a
valuation or a fraud verdict.
"""

from __future__ import annotations

from typing import Any

from agents.tools import READ_ONLY, AgentTool, AgentToolRegistry

TOOL_NAME = "property.intelligence"

# Public-safe surface exposed to an agent (no fraud/graph/KYC internals).
_LIGHT_KEYS = (
    "room_id",
    "score",
    "confidence",
    "score_version",
    "computed_at",
    "strengths",
    "suggestions",
    "disclaimer",
)


def _property_intelligence_executor(
    context: dict[str, Any], room_id: int, include_breakdown: bool = False
):
    from rooms.models import Room

    from .engine import get_property_intelligence, public_payload

    if not Room.objects.filter(pk=room_id).exists():
        return {"ok": False, "error": f"room {room_id!r} not found"}

    try:
        payload = public_payload(get_property_intelligence(room_id))
    except Room.DoesNotExist:
        return {"ok": False, "error": f"room {room_id!r} not found"}
    except Exception as exc:  # engine never raises on live data paths
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if not include_breakdown:
        return {"ok": True, "data": {key: payload[key] for key in _LIGHT_KEYS if key in payload}}
    return {"ok": True, "data": payload}


def register_property_intelligence_tool() -> None:
    """Register ``property.intelligence`` in the Phase 19.0 tool registry."""
    AgentToolRegistry.register(
        AgentTool(
            name=TOOL_NAME,
            description=(
                "Return the Rentora Property Intelligence score for a listing. "
                "The score is 0-100, transparent and deterministic; it is an "
                "informational indicator, NOT a property valuation, fraud "
                "verdict, or guarantee of rental performance. This tool's "
                "output is the authoritative score — never invent or restate "
                "it from other data."
            ),
            input_schema={
                "type": "object",
                "required": ["room_id"],
                "additionalProperties": False,
                "properties": {
                    "room_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Rentora room/listing identifier",
                    },
                    "include_breakdown": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Include the full per-category breakdown "
                            "(score, weight, contribution, availability)."
                        ),
                    },
                },
            },
            capability=READ_ONLY,
            executor=_property_intelligence_executor,
            owner="rentora.property_intelligence",
        )
    )
