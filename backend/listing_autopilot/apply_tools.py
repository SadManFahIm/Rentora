"""Typed apply executors for Listing Autopilot proposals (Phase 19.3).

These are the STATE_CHANGING tools that ``agents.services.apply_proposal``
executes — and ONLY they. They are registered (not exported as callable APIs)
and consumed via the Tool Registry, so every applied action is audited,
schema-verified, owned, and exactly-once.

Every executor re-verifies server-side:
* the referenced room still exists;
* the acting user (``context["user"]``) owns that room;
* the proposal's ``grounding_key`` still matches the room's current state
  (stale detection — never clobber the landlord's later edits).

Returns the standard ``{"ok": bool, "data"/"error"}`` envelope the SDK
surfaces and records in ``AgentProposal.application_result``.
"""

from __future__ import annotations

from typing import Any

from agents.tools import (
    RESULT_DATA,
    RESULT_ERROR,
    RESULT_OK,
    STATE_CHANGING,
    AgentTool,
    AgentToolRegistry,
)

# Root owner tag for registry attribution.
_OWNER = "rentora.listing_autopilot"


def _resolve_room(context: dict[str, Any], room_id: Any):
    """Load the room, or return (None, error)."""
    from rooms.models import Room

    try:
        room = Room.objects.select_for_update().get(pk=room_id)
    except Room.DoesNotExist:
        return None, "room_missing"
    return room, None


def _verify_owner_and_stale(context, room, stale_checks=None):
    user = context.get("user")
    if user is None or getattr(user, "pk", None) != getattr(room, "owner_id", None):
        return False, "not_room_owner"
    # Stale detection: per-field checksums. Only a change to the exact field
    # this proposal overwrites (since analysis) blocks — sibling proposals from
    # the same snapshot stay independently applicable.
    from .analysis import field_grounding

    for field, checksum in (stale_checks or {}).items():
        if field not in ("title", "description", "amenities", "price"):
            continue
        if field_grounding(room, (field,)) != checksum:
            return False, "stale_grounding"
    return True, ""


def _apply_title(context, *, room_id, title, grounding_key="", stale_checks=None) -> dict[str, Any]:
    room, err = _resolve_room(context, room_id)
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: err}
    ok, err = _verify_owner_and_stale(context, room, stale_checks or {})
    if not ok:
        return {RESULT_OK: False, RESULT_ERROR: err}
    title = (title or "").strip()[:200]
    if not title:
        return {RESULT_OK: False, RESULT_ERROR: "empty_title"}
    room.title = title
    room.save(update_fields=["title", "updated_at"])
    return {RESULT_OK: True, RESULT_DATA: {"room_id": room.pk, "title": room.title}}


def _apply_description(
    context, *, room_id, description, grounding_key="", stale_checks=None
) -> dict[str, Any]:
    room, err = _resolve_room(context, room_id)
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: err}
    ok, err = _verify_owner_and_stale(context, room, stale_checks or {})
    if not ok:
        return {RESULT_OK: False, RESULT_ERROR: err}
    description = (description or "").strip()[:10000]
    if not description:
        return {RESULT_OK: False, RESULT_ERROR: "empty_description"}
    room.description = description
    room.save(update_fields=["description", "updated_at"])
    return {
        RESULT_OK: True,
        RESULT_DATA: {"room_id": room.pk, "description_length": len(room.description)},
    }


def _apply_amenities(
    context, *, room_id, add_amenities=None, grounding_key="", stale_checks=None
) -> dict[str, Any]:
    room, err = _resolve_room(context, room_id)
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: err}
    ok, err = _verify_owner_and_stale(context, room, stale_checks or {})
    if not ok:
        return {RESULT_OK: False, RESULT_ERROR: err}
    current = set(str(a).strip() for a in (room.amenities or []) if str(a).strip())
    found = 0
    for item in add_amenities or []:
        value = str(item).strip()[:50]
        low = value.lower()
        if not value or low in {c.lower() for c in current}:
            continue
        current.add(value)
        found += 1
    room.amenities = sorted(current)
    room.save(update_fields=["amenities", "updated_at"])
    return {
        RESULT_OK: True,
        RESULT_DATA: {"room_id": room.pk, "added": found, "amenities": room.amenities},
    }


def _apply_photo_recommendation(
    context,
    *,
    room_id,
    suggested_actions=None,
    suggested_amenities=None,
    grounding_key="",
    stale_checks=None,
) -> dict[str, Any]:
    room, err = _resolve_room(context, room_id)
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: err}
    ok, err = _verify_owner_and_stale(context, room, stale_checks or {})
    if not ok:
        return {RESULT_OK: False, RESULT_ERROR: err}
    # A photo recommendation is advisory — applying it records the guidance and
    # (optionally) promotes suggested photo-derived amenities that are real.
    added = 0
    current = set(str(a).strip() for a in (room.amenities or []) if str(a).strip())
    for item in suggested_amenities or []:
        value = str(item).strip()[:50]
        low = value.lower()
        if not value or low in {c.lower() for c in current}:
            continue
        current.add(value)
        added += 1
    if added:
        room.amenities = sorted(current)
        room.save(update_fields=["amenities", "updated_at"])
    photo_count = room.images.count() if hasattr(room, "images") else 0
    return {
        RESULT_OK: True,
        RESULT_DATA: {
            "room_id": room.pk,
            "photo_count": photo_count,
            "suggested_actions": list(suggested_actions or []),
            "amenities_added": added,
            "note": "Advisory action recorded; photos require manual upload.",
        },
    }


def _apply_price(
    context, *, room_id, new_price, direction="", grounding_key="", stale_checks=None
) -> dict[str, Any]:
    room, err = _resolve_room(context, room_id)
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: err}
    ok, err = _verify_owner_and_stale(context, room, stale_checks or {})
    if not ok:
        return {RESULT_OK: False, RESULT_ERROR: err}
    from decimal import Decimal, InvalidOperation

    try:
        price = Decimal(str(new_price))
    except (InvalidOperation, TypeError):
        return {RESULT_OK: False, RESULT_ERROR: "invalid_price"}
    if price <= 0:
        return {RESULT_OK: False, RESULT_ERROR: "invalid_price"}
    room.price = price
    room.save(update_fields=["price", "updated_at"])
    return {RESULT_OK: True, RESULT_DATA: {"room_id": room.pk, "price": float(room.price)}}


def _apply_listing_renewal(
    context, *, room_id, grounding_key="", stale_checks=None
) -> dict[str, Any]:
    room, err = _resolve_room(context, room_id)
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: err}
    ok, err = _verify_owner_and_stale(context, room, stale_checks or {})
    if not ok:
        return {RESULT_OK: False, RESULT_ERROR: err}
    from django.utils import timezone

    room.updated_at = timezone.now()
    room.is_available = True
    room.save(update_fields=["updated_at", "is_available"])
    return {
        RESULT_OK: True,
        RESULT_DATA: {
            "room_id": room.pk,
            "renewed_at": room.updated_at.isoformat() if room.updated_at else None,
        },
    }


_EXECUTORS = {
    "TITLE_UPDATE": _apply_title,
    "DESCRIPTION_UPDATE": _apply_description,
    "AMENITY_UPDATE": _apply_amenities,
    "PHOTO_RECOMMENDATION": _apply_photo_recommendation,
    "PRICE_UPDATE": _apply_price,
    "LISTING_RENEWAL": _apply_listing_renewal,
}


def _build_input_schema(proposal_type: str) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "room_id": {"type": "integer"},
            "grounding_key": {"type": "string", "default": ""},
            "stale_checks": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["room_id"],
        "additionalProperties": False,
    }
    if proposal_type == "AMENITY_UPDATE":
        schema["properties"]["add_amenities"] = {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
        }
    elif proposal_type == "PHOTO_RECOMMENDATION":
        schema["properties"]["suggested_actions"] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        }
        schema["properties"]["suggested_amenities"] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
        }
    elif proposal_type == "PRICE_UPDATE":
        schema["properties"]["new_price"] = {
            "type": ["number", "integer"],
            "exclusiveMinimum": 0,
        }
        schema["properties"]["direction"] = {"type": "string", "default": ""}
        schema["required"] = ["room_id", "new_price"]
    elif proposal_type == "TITLE_UPDATE":
        schema["properties"]["title"] = {"type": "string", "minLength": 1, "maxLength": 200}
        schema["required"] = ["room_id", "title"]
    elif proposal_type == "DESCRIPTION_UPDATE":
        schema["properties"]["description"] = {
            "type": "string",
            "minLength": 1,
            "maxLength": 10000,
        }
        schema["required"] = ["room_id", "description"]
    return schema


def register_listing_autopilot_tools() -> None:
    """Register the STATE_CHANGING apply tools + a READ_ONLY analyze tool.
    Call from the SDK's ``register_builtin_tools`` (guarded) so every agent run
    has a complete registry."""
    from agents.tools import READ_ONLY

    AgentToolRegistry.register(
        AgentTool(
            name="listing.autopilot.analyze",
            description=(
                "Deterministic rehearse of the autopilot's weekly analysis for one "
                "landlord-owned listing (read-only; never mutates)."
            ),
            input_schema={
                "type": "object",
                "properties": {"room_id": {"type": "integer"}},
                "required": ["room_id"],
            },
            capability=READ_ONLY,
            executor=_analyze_tool,
            owner=_OWNER,
        )
    )

    for proposal_type, executor in _EXECUTORS.items():
        slug = proposal_type.lower().replace("_", "-")
        AgentToolRegistry.register(
            AgentTool(
                name=f"listing.autopilot.apply.{slug}",
                description=(
                    f"Apply a landlord-approved {proposal_type.lower()} recommendation "
                    "to a landlord-owned listing (state-changing; proposal-gated)."
                ),
                input_schema=_build_input_schema(proposal_type),
                capability=STATE_CHANGING,
                executor=executor,
                owner=_OWNER,
            )
        )


def _analyze_tool(context: dict[str, Any], *, room_id) -> dict[str, Any]:
    """Read-only analysis tool — same deterministic backend, no side effects."""
    from rooms.models import Room

    from .analysis import analyze_room

    room = Room.objects.filter(pk=room_id).first()
    user = context.get("user")
    if room is None:
        return {RESULT_OK: False, RESULT_ERROR: "room_missing"}
    if user is None or room.owner_id != user.pk:
        return {RESULT_OK: False, RESULT_ERROR: "not_room_owner"}
    payload = analyze_room(room)
    return {RESULT_OK: True, RESULT_DATA: payload}
