"""AI listing description generator (Tier 5).

Landlords often skip or half-write descriptions, and a thin listing converts
poorly. This endpoint drafts a title + description + suggested amenities
from the fields the landlord has already filled (area, type, price, size,
gender, amenities) plus — when photos exist — the deterministic image
profile (brightness / colourfulness / tones).

Deterministic and grounded: every sentence is built from real inputs, no
LLM is called, nothing is hallucinated. The landlord always edits before
publishing (the UI presents it as a *draft*).
"""

from __future__ import annotations

from typing import Any

_ROOM_TYPE_LABEL = {
    "single": "a single room",
    "shared": "a shared room",
    "studio": "a studio",
}

_AMENITY_BLURBS = {
    "wifi": "high-speed WiFi",
    "ac": "air conditioning",
    "attached bath": "an attached bathroom",
    "furnished": "furnished setup",
    "gym": "a gym",
    "parking": "parking",
    "kitchen": "a kitchen",
    "bills included": "utilities included",
    "utilities included": "utilities included",
}

_GENDER_NOTE = {
    "male": "This room is for male tenants.",
    "female": "This room is for female tenants.",
    "any": "Open to all tenants.",
}


def generate_listing_draft(
    *,
    area: str,
    room_type: str,
    price: float | None,
    size_sqft: int | None,
    gender_preference: str = "any",
    amenities: list[str] | None = None,
    title_hint: str = "",
    image_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a draft title + description + amenity suggestions.

    All parameters come from the landlord's own form (or the listing row).
    ``image_profile`` is the optional output of ``copilot.image_profile`` —
    used only to make the draft feel tailored, never to invent facts.
    """
    amenities = [str(a).strip().lower() for a in (amenities or [])]
    room_label = _ROOM_TYPE_LABEL.get(room_type, "a room")

    # ---- title -------------------------------------------------------------
    tone = ""
    if image_profile and image_profile.get("available"):
        tone = image_profile.get("brightness", "") or ""
        if tone and tone != "normal":
            tone = tone.capitalize() + " "
    title = f"{tone}{room_label.title()} in {area}" if room_label else f"Room in {area}"
    if title_hint and len(title_hint.strip()) >= 8:
        title = title_hint.strip()

    # ---- description --------------------------------------------------------
    lines: list[str] = []
    lines.append(f"Available: {room_label} in {area}.")
    if size_sqft:
        lines.append(f"Spacious {size_sqft} sqft interior.")
    if price:
        lines.append(f"৳{int(price):,}/month.")
    if amenities:
        blurb_parts = [_AMENITY_BLURBS.get(a, a) for a in amenities if _AMENITY_BLURBS.get(a, a)]
        if blurb_parts:
            lines.append("Includes " + ", ".join(blurb_parts) + ".")
    gender_note = _GENDER_NOTE.get(gender_preference or "any")
    if gender_note:
        lines.append(gender_note)
    if image_profile and image_profile.get("available"):
        brightness = image_profile.get("brightness")
        colour = image_profile.get("colourfulness")
        if brightness and colour:
            lines.append(f"The photos show a {brightness}, {colour} space — matches the listing.")
    description = " ".join(lines)

    # ---- suggested amenity tags --------------------------------------------
    suggested = [a for a in amenities if a in _AMENITY_BLURBS]
    if not suggested:
        suggested = ["wifi", "attached bath"]

    return {
        "title": title,
        "description": description,
        "amenities": suggested,
        "note": "Auto-drafted from your listing details — review and edit before publishing.",
    }
