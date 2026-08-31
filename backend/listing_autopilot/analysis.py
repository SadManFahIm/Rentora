"""Deterministic listing analysis for the autopilot (Phase 19.3).

This module owns every *decision* the autopilot makes: eligibility, content
gaps, photo gaps, price recommendation, and renewal. It NEVER invents data —
each signal is delegated to an existing, authoritative engine:

* listing quality   -> ``rooms.listing_quality.get_listing_quality``
* Property score    -> ``property_intelligence.engine.get_property_intelligence``
* price             -> ``rooms.price_recommendation.listing_price_recommendation``
* photo gaps        -> ``rooms.vision.analyze_listing`` (suggested amenities)
* content gaps      -> the listing-quality category scores (never re-derived)

Eligibility rules that already exist in the product (entitlement, ownership,
availability) take precedence over anything invented here. The single public
entrypoint ``analyze_room`` returns a grounded payload plus a stable
``grounding_key`` used to detect stale proposals at apply time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.utils import timezone

from . import constants as C

logger = logging.getLogger(__name__)

# Fields each proposal type may overwrite. Staleness is checked per-field so
# applying one sibling proposal never invalidates another from the same
# analysis (only a landlord edit to the exact field being overwritten blocks).
_STALE_FIELDS = {
    "TITLE_UPDATE": ("title",),
    "DESCRIPTION_UPDATE": ("description",),
    "AMENITY_UPDATE": ("amenities",),
    "PHOTO_RECOMMENDATION": (),
    "PRICE_UPDATE": ("price",),
    "LISTING_RENEWAL": (),
}


def stale_fields(proposal_type: str) -> tuple[str, ...]:
    return _STALE_FIELDS.get(proposal_type, ())


# Reservation-free wording for renewal — never promises a ranking boost.
_RENEWAL_NOTE = (
    "Your listing hasn't been updated in a while and recent interest is low. "
    "Renewing refreshes its recency for search without changing any content."
)


def grounding_key(room) -> str:
    """Stable hash of the immutable room state a recommendation is grounded on.

    Used to detect stale proposals: if the room changed after the analysis was
    written (title/description/amenities/price/etc.), the key differs and the
    apply service refuses to blindly overwrite the landlord's edit.
    """
    room_core = {
        "id": room.pk,
        "title": (room.title or ""),
        "description": (room.description or ""),
        "price": str(room.price),
        "amenities": [str(a).strip().lower() for a in (room.amenities or [])],
        "is_available": bool(room.is_available),
        "gender_preference": room.gender_preference,
        "size_sqft": room.size_sqft,
        "updated_at": (room.updated_at.isoformat() if room.updated_at else ""),
    }
    blob = json.dumps(room_core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def field_grounding(room, fields: tuple[str, ...]) -> str:
    """Checksum over a *subset* of room fields.

    Used for apply-time staleness so a proposal only blocks when the exact
    field it intends to overwrite changed since analysis (sibling proposals
    from the same snapshot remain independently applicable).
    """
    values = {}
    for name in fields:
        if name in ("title", "description"):
            values[name] = str(getattr(room, name) or "")
        elif name == "amenities":
            values[name] = [str(a).strip().lower() for a in (room.amenities or [])]
        elif name == "price":
            values[name] = str(room.price)
    blob = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _key_amenities(amenities: list[str]) -> set[str]:
    return {str(a).strip().lower() for a in amenities if a}


def _build_title_draft(room) -> str | None:
    """Grounded, deterministic title suggestion.

    Built only from stored room fields (area, room_type, size, key amenity) via
    the existing description-draft generator — never invented facts. Returns
    None when the current title is already good or no meaningful variant exists.
    """

    area_label = room.get_area_display() or (room.area or "")
    room_type_label = room.get_room_type_display() or room.room_type
    key = _key_amenities(room.amenities or [])
    amenity = "Furnished " if "furnished" in key else ""
    studio = "Studio" if room.room_type == "studio" else room_type_label.capitalize()
    candidate = f"{amenity}{studio} in {area_label}"
    # Don't churn a title that already mentions the area and is short enough.
    current = (room.title or "").strip()
    if area_label and area_label.lower() in current.lower():
        return None
    if len(candidate) > 200:
        return None
    return candidate


def _build_description_draft(room) -> str | None:
    """Grounded description draft via the existing generator (no LLM)."""
    from rooms.description_generator import generate_listing_draft

    draft = generate_listing_draft(
        area=room.area or "",
        room_type=room.room_type or "",
        price=float(room.price),
        size_sqft=room.size_sqft,
        gender_preference=room.gender_preference or "any",
        amenities=[str(a) for a in (room.amenities or [])],
        title_hint=(room.title or "")[:200],
    )
    description = (draft.get("description") or "").strip()
    current = (room.description or "").strip()
    if not description or (current and len(current) >= C.GOOD_DESCRIPTION_LEN):
        return None
    return description


def _photo_recommendation(room, quality: dict[str, Any]) -> dict[str, Any] | None:
    """Photo gaps from quality/primary/photos + vision suggested amenities.

    Returns a typed payload or None when no photo action is warranted.
    """
    actions: list[str] = []
    image_count = room.images.count() if hasattr(room, "images") else 0
    has_primary = (
        bool(room.images.filter(is_primary=True).exists()) if hasattr(room, "images") else False
    )
    if image_count < C.MIN_PHOTO_COUNT:
        actions.append("add photos")
    elif has_primary is False:
        actions.append("set a primary photo")
    if image_count < C.GOOD_PHOTO_COUNT:
        actions.append(f"reach at least {C.GOOD_PHOTO_COUNT} photos")

    suggested = []
    try:
        from rooms.vision import analyze_listing

        vision = analyze_listing(room)
        if vision.get("available"):
            suggested = [str(a) for a in (vision.get("suggested_amenities") or [])][:5]
    except Exception:  # pragma: no cover - vision never raises on live paths
        suggested = []

    if not actions and not suggested:
        return None
    return {
        "type": "PHOTO_RECOMMENDATION",
        "photo_count": image_count,
        "has_primary": has_primary,
        "suggested_actions": actions,
        "suggested_amenities": suggested,
    }


def _price_payload(room) -> dict[str, Any]:
    """Reuse the Phase 15 price engine; never re-derive pricing here."""
    from rooms.price_recommendation import listing_price_recommendation

    try:
        return listing_price_recommendation(room)
    except Exception:
        logger.exception("price recommendation failed for room %s", room.pk)
        return {}


def _property_payload(room) -> dict[str, Any]:
    """Reuse the Phase 19.1 Property Intelligence public payload."""
    from property_intelligence.engine import get_property_intelligence, public_payload

    try:
        return public_payload(get_property_intelligence(room))
    except Exception:
        logger.exception("property intelligence failed for room %s", room.pk)
        return {}


def _eligibility(room) -> tuple[bool, list[str]]:
    """Deterministic eligibility — existing product rules take precedence."""
    blocks: list[str] = []
    if not getattr(room, "is_available", True):
        blocks.append("listing_unavailable")
    if room.owner_id is None or getattr(room.owner, "role", "") != "landlord":
        if getattr(room.owner, "is_staff", False):
            pass  # staff can test the autopilot
        else:
            blocks.append("owner_not_landlord")
    if not room.area or not room.room_type:
        blocks.append("missing_required_fields")
    return (not blocks, blocks)


def analyze_room(
    room,
    *,
    privilege_bypass: bool = False,
) -> dict[str, Any]:
    """Full deterministic analysis for one listing (never raises).

    ``privilege_bypass`` is for staff/testing and skips the landlord-role
    eligibility gate only (availability/missing fields still apply).
    Returns a dict with ``eligible`` and ``recommendations`` (typed payloads).
    """
    from rooms.listing_quality import get_listing_quality

    quality = get_listing_quality(room) if hasattr(room, "images") else {}
    quality_score = quality.get("score")
    category = quality.get("category_scores") or {}

    pi = _property_payload(room)
    price = _price_payload(room)

    now = timezone.now()
    stale_days = (now.date() - room.updated_at.date()).days if room.updated_at else 0
    stale_threshold = C.AutopilotSettings().stale_threshold_days

    eligible, blocks = _eligibility(room)
    if privilege_bypass and "owner_not_landlord" in blocks:
        blocks = [b for b in blocks if b != "owner_not_landlord"]
        eligible = not blocks

    recommendations: list[dict[str, Any]] = []
    if eligible:
        # --- title (grounded draft) -----------------------------------------
        if category.get("description", 0) < 0.5 or not (room.title or "").strip():
            draft_title = _build_title_draft(room)
            if draft_title:
                recommendations.append(
                    {
                        "type": "TITLE_UPDATE",
                        "current_title": (room.title or ""),
                        "suggested_title": draft_title,
                        "reason": "The current title is sparse for a market-ready listing.",
                    }
                )

        # --- description ------------------------------------------------------
        desc = _build_description_draft(room)
        if desc:
            recommendations.append(
                {
                    "type": "DESCRIPTION_UPDATE",
                    "current_length": len((room.description or "").strip()),
                    "suggested_description": desc,
                    "reason": "Description is thin — a fuller, grounded write-up improves the card.",
                }
            )

        # --- amenities ---------------------------------------------------------
        amenity_score = category.get("amenities", 1.0)
        current = _key_amenities(room.amenities or [])
        suggested = [a for a in ("wifi", "ac", "parking", "kitchen") if a not in current]
        if amenity_score < 0.75 and suggested:
            recommendations.append(
                {
                    "type": "AMENITY_UPDATE",
                    "current_amenities": [str(a) for a in (room.amenities or [])],
                    "suggested_additions": suggested,
                    "reason": "Adding common, verifiable amenities may improve search fit.",
                }
            )

        # --- photos -------------------------------------------------------------
        ph = _photo_recommendation(room, quality)
        if ph:
            recommendations.append(ph)

        # --- price ---------------------------------------------------------------
        price_direction = price.get("direction", "hold")
        dynamic = price.get("dynamic_price")
        if price_direction in ("raise", "lower") and dynamic:
            recommendations.append(
                {
                    "type": "PRICE_UPDATE",
                    "current_price": float(room.price),
                    "suggested_price": float(dynamic),
                    "direction": price_direction,
                    "confidence": price.get("confidence", "low"),
                    "reasons": price.get("reasons", [])[:4],
                    "window": price.get("window"),
                    "valid_until": price.get("valid_until"),
                    "note": price.get("note", ""),
                }
            )

        # --- renewal --------------------------------------------------------------
        interest = price.get("signals", {}).get("interest_30d", {}).get("total", 0)
        if stale_days >= stale_threshold and interest == 0:
            recommendations.append(
                {
                    "type": "LISTING_RENEWAL",
                    "stale_days": stale_days,
                    "recent_interest": interest,
                    "note": _RENEWAL_NOTE,
                }
            )

    grounding = grounding_key(room) if eligible else ""
    # Wait for the analysis to persist the snapshot — compute the full payload.
    payload = {
        "room_id": room.pk,
        "eligible": eligible,
        "eligibility_blocks": blocks,
        "listing_quality": {
            "score": quality_score,
            "level": quality.get("level"),
            "categories": category,
        },
        "property_intelligence": {
            "score": pi.get("score"),
            "confidence": pi.get("confidence"),
        },
        "price": {
            "direction": price.get("direction", "hold"),
            "suggested": price.get("dynamic_price") or price.get("suggested_price"),
            "confidence": price.get("confidence", "low"),
        },
        "stale_days": stale_days,
        "stale_threshold_days": stale_threshold,
        "photo_count": room.images.count() if hasattr(room, "images") else 0,
        "recommendations": recommendations,
        "grounding_key": grounding,
    }
    return payload
