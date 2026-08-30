"""Rentora AI Rental Agent domain tools — Phase 19.2.

Five ground-truth tools registered through the Phase 19.0
``AgentToolRegistry``:

* ``search.list_rooms``  (read)  — grounded room discovery over the existing
  Copilot/room pipeline. Never invents a listing: every card comes from a
  retrieved ``Room`` row.
* ``room.by_id``         (read)  — public card + insight for one listing.
* ``area.commute``       (read)  — commute estimate between a room/area and a
  destination area, straight from ``rooms.map_intel.commute_eta``. When no
  estimate exists it is reported as ``available: false`` — never invented.
* ``price.compare``      (read)  — market price comparison from
  ``pricing.services.insight.get_price_insight``. No market segment →
  ``available: false``.
* ``bookmark.create``   (state_changing) — saves a listing to the user's
  wishlist. STATE_CHANGING, so the session turns every call into a human
  review proposal; it only ever executes through the idempotent
  ``apply_proposal`` path with the conversation owner as the acting user
  (the executor never accepts a user in its arguments — no cross-account
  writes are possible).
"""

from __future__ import annotations

from typing import Any

from agents.tools import READ_ONLY, STATE_CHANGING, AgentTool, AgentToolRegistry

SEARCH_TOOL = "search.list_rooms"
ROOM_TOOL = "room.by_id"
COMMUTE_TOOL = "area.commute"
PRICE_TOOL = "price.compare"
BOOKMARK_TOOL = "bookmark.create"

RENTAL_TOOL_NAMES = (SEARCH_TOOL, ROOM_TOOL, COMMUTE_TOOL, PRICE_TOOL, BOOKMARK_TOOL)

SEARCH_MAX_TOP_K = 10
_COMMUTE_MODES = ("walking", "driving", "transit")


# ---------------------------------------------------------------------------
# Executors — every one returns the ``{"ok": bool, "data": {...}}`` envelope.
# Domain "no data" cases (no market segment, no transit route) are *successful*
# truthful answers (``ok: True, data.available: False``), never errors — an
# error envelope counts as a tool failure in the session guardrails.
# ---------------------------------------------------------------------------


def _search_executor(
    context: dict[str, Any],
    query: str = "",
    budget_max: int | None = None,
    area: str = "",
    room_type: str = "",
    gender_preference: str = "",
    amenities: list[str] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    from copilot.services import extract_intent, retrieve_rooms

    intent = extract_intent(query or "")
    if budget_max:
        intent["budget_max"] = budget_max
    if area:
        intent["areas"] = [area]
    if room_type:
        intent["room_type"] = room_type
    if gender_preference:
        intent["gender"] = gender_preference
    if amenities:
        intent["amenities"] = list(dict.fromkeys([*intent.get("amenities", []), *amenities]))[:8]

    rooms, total_count, kind = retrieve_rooms(
        intent, context.get("user"), top_k=max(1, min(top_k, SEARCH_MAX_TOP_K))
    )

    from .services import room_card

    return {
        "ok": True,
        "data": {
            "total_count": total_count,
            "returned": len(rooms),
            "kind": kind,
            "filters": {
                "budget_max": intent.get("budget_max"),
                "areas": intent.get("areas") or [],
                "room_type": intent.get("room_type"),
                "gender_preference": intent.get("gender"),
                "amenities": intent.get("amenities") or [],
            },
            "rooms": [room_card(r) for r in rooms],
        },
    }


def _room_executor(
    context: dict[str, Any],
    room_id: int,
    include_insights: bool = True,
) -> dict[str, Any]:
    from rooms.models import Room

    room = (
        Room.objects.select_related("owner").prefetch_related("images").filter(pk=room_id).first()
    )
    if room is None:
        return {"ok": False, "error": f"room {room_id!r} not found"}
    if not room.is_available:
        # Honest, not an error: listing exists but isn't bookable right now.
        return {
            "ok": True,
            "data": {
                "available": False,
                "reason": "listing is currently unavailable",
                "room_id": room_id,
            },
        }

    from .services import room_card, room_insights

    data: dict[str, Any] = room_card(room)
    if include_insights:
        data["insights"] = room_insights(room)
    return {"ok": True, "data": data}


def _commute_executor(
    context: dict[str, Any],
    room_id: int | None = None,
    from_area: str = "",
    to_area: str = "",
    mode: str = "walking",
    include_metro_score: bool = True,
) -> dict[str, Any]:
    from rooms.map_intel import commute_eta, metro_access_score
    from rooms.models import Room
    from rooms.streets import area_center

    if mode not in _COMMUTE_MODES:
        return {"ok": False, "error": f"mode must be one of {', '.join(_COMMUTE_MODES)}"}

    source_label = ""
    source: tuple[float, float] | None = None
    if room_id:
        room = Room.objects.filter(pk=room_id).first()
        if room is None:
            return {"ok": False, "error": f"room {room_id!r} not found"}
        source = (float(room.lat), float(room.lng))
        source_label = room.title
    elif from_area:
        center = area_center(from_area)
        if center is not None:
            source = center
            source_label = from_area
    if source is None:
        return {
            "ok": True,
            "data": {
                "available": False,
                "reason": "could not resolve the origin (pass a valid room_id or a known area)",
                "mode": mode,
                "minutes": None,
                "distance_km": None,
                "estimate": False,
                "detail": "origin could not be resolved",
                "origin": from_area or str(room_id or ""),
                "destination": to_area,
            },
        }

    destination = area_center(to_area)
    if destination is None:
        return {
            "ok": True,
            "data": {
                "available": False,
                "reason": f"destination area {to_area!r} is not in the location gazetteer",
                "mode": mode,
                "minutes": None,
                "distance_km": None,
                "estimate": False,
                "detail": "unknown destination area",
                "origin": source_label or "selected area",
                "destination": to_area,
            },
        }

    estimate = commute_eta(source[0], source[1], destination[0], destination[1], mode=mode)
    data: dict[str, Any] = {
        "available": estimate.minutes is not None,
        "mode": estimate.mode,
        "minutes": estimate.minutes,
        "distance_km": estimate.distance_km,
        "estimate": estimate.estimate,
        "detail": estimate.detail,
        "origin": source_label or "selected area",
        "destination": to_area,
    }
    if include_metro_score:
        data["origin_metro_access_score"] = metro_access_score(source[0], source[1])
    return {"ok": True, "data": data}


def _price_executor(context: dict[str, Any], room_id: int) -> dict[str, Any]:
    from pricing.services.insight import get_price_insight
    from rooms.models import Room

    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        return {"ok": False, "error": f"room {room_id!r} not found"}
    insight = get_price_insight(room)
    if insight is None:
        return {
            "ok": True,
            "data": {
                "available": False,
                "reason": "no market segment yet for this (area, room_type) — "
                "fewer than 3 comparable listings",
            },
        }
    return {
        "ok": True,
        "data": {
            "available": True,
            "room_id": room_id,
            "area": room.area,
            "room_type": room.room_type,
            "listed_price": insight.get("your_price"),
            "market_average": insight.get("avg_price"),
            "percentage_diff": insight.get("percentage_diff"),
            "classification": insight.get("classification"),
            "message": insight.get("message"),
            "sample_size": insight.get("sample_size"),
        },
    }


def _bookmark_executor(context: dict[str, Any], room_id: int) -> dict[str, Any]:
    """Save a listing to the *acting* user's wishlist.

    Only ever invoked through ``agents.services.apply_proposal``, with
    ``context["user"]`` set to the proposal's conversation owner by the SDK.
    Idempotent: saving the same room twice is a no-op (the wishlist table has
    a unique (user, room) constraint).
    """
    from rooms.models import Room
    from wishlist.models import Wishlist

    user = context.get("user")
    if user is None or not getattr(user, "is_authenticated", False):
        return {"ok": False, "error": "bookmark requires an authenticated user"}

    room = Room.objects.filter(pk=room_id, is_available=True).first()
    if room is None:
        return {"ok": False, "error": f"room {room_id!r} not found or not available"}

    _, created = Wishlist.objects.get_or_create(user=user, room=room)
    return {
        "ok": True,
        "data": {
            "room_id": room_id,
            "saved": True,
            "already_saved": not created,
            "card": None,  # filled by the caller for the consent UI when needed
        },
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_rental_agent_tools() -> None:
    """Register all Phase 19.2 domain tools (idempotent)."""

    AgentToolRegistry.register(
        AgentTool(
            name=SEARCH_TOOL,
            description=(
                "Search available Rentora room listings. Query is free text "
                'in Bangla, English or Banglish (e.g. "উত্তরায় ১০ হাজারের '
                'মধ্যে furnished room"). Every room returned is a real, '
                "currently available listing; never invent rooms. Pass "
                "structured filters to narrow the search. Returns the applied "
                "filters plus up to top_k room cards."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search in Bangla/English/Banglish",
                    },
                    "budget_max": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Maximum monthly rent in BDT",
                    },
                    "area": {
                        "type": "string",
                        "description": "Dhaka area name, e.g. Dhanmondi, Mirpur, Uttara",
                    },
                    "room_type": {
                        "type": "string",
                        "enum": ["single", "shared", "studio"],
                        "description": "Listing type filter",
                    },
                    "gender_preference": {
                        "type": "string",
                        "enum": ["any", "male", "female"],
                        "description": "Gender preference filter",
                    },
                    "amenities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required amenities, e.g. Furnished, AC, Internet",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                        "description": "Max room cards to return",
                    },
                },
            },
            capability=READ_ONLY,
            executor=_search_executor,
            owner="rentora.rental_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=ROOM_TOOL,
            description=(
                "Return the public card for one Rentora room by id, including "
                "price, area, type, amenities, verification, proximity and — "
                "when include_insights is on — its market price comparison, "
                "nearby landmarks and Property Intelligence badge. The data "
                "comes only from stored room fields; never invent details. "
                "An unavailable listing reports available:false instead."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["room_id"],
                "properties": {
                    "room_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Rentora room/listing identifier",
                    },
                    "include_insights": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include price insight, landmarks and "
                        "Property Intelligence badge",
                    },
                },
            },
            capability=READ_ONLY,
            executor=_room_executor,
            owner="rentora.rental_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=COMMUTE_TOOL,
            description=(
                "Estimate travel time between a room (room_id) or area "
                "(from_area) and a destination Dhaka area via walking, driving "
                "or transit. Returns minutes as an ESTIMATE — it is a heuristic, "
                "not a live map result. When no estimate can be computed "
                "(unknown area, or transit ends not near an MRT station) "
                "available is false and you must tell the user the data is not "
                "available rather than invent a number."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["to_area"],
                "properties": {
                    "room_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Origin room (its coordinates)",
                    },
                    "from_area": {
                        "type": "string",
                        "description": "Origin area name when no room_id is given",
                    },
                    "to_area": {
                        "type": "string",
                        "description": "Destination Dhaka area name",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["walking", "driving", "transit"],
                        "default": "walking",
                    },
                    "include_metro_score": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include the origin's 0-100 metro access score",
                    },
                },
            },
            capability=READ_ONLY,
            executor=_commute_executor,
            owner="rentora.rental_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=PRICE_TOOL,
            description=(
                "Compare one room's listed price against its market segment "
                "(same area + room type) and return the percentage difference "
                "and a plain-English classification. When no big-enough market "
                "segment exists yet, available is false and you must say the "
                "comparison isn't available — never estimate the market yourself."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["room_id"],
                "properties": {
                    "room_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Rentora room/listing identifier",
                    }
                },
            },
            capability=READ_ONLY,
            executor=_price_executor,
            owner="rentora.rental_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=BOOKMARK_TOOL,
            description=(
                "Save a room to the user's bookmarks (wishlist). This is a "
                "state-changing action: the call creates a pending consent "
                "request instead of executing, and the user must approve it "
                "in the chat before anything is saved. Ask the user for "
                "explicit confirmation BEFORE calling this tool, and clearly "
                "explain what will be saved and how to undo it."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["room_id"],
                "properties": {
                    "room_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Rentora room/listing identifier to save",
                    }
                },
            },
            capability=STATE_CHANGING,
            executor=_bookmark_executor,
            owner="rentora.rental_agent",
        )
    )
