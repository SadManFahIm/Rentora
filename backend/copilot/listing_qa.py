"""RAG listing Q&A — grounded answers about a *single* listing (Tier 3).

The Copilot's original search mode retrieves rooms and answers over them.
This module extends that with a **listing mode**: the user asks about one
specific listing (usually from the "Ask Copilot about this listing" button
in the room modal), and the answer is generated strictly over that one
room's database row — the retrieval step is the listing itself.

The rules are deterministic and conservative:

* An aspect question (price / area / amenities / …) is answered **only**
  when the listing actually carries that data. If the field is empty or the
  question can't be mapped to a real fact, the Copilot says so — it never
  fills gaps with guesses.
* A question with no detectable aspect falls back to a factual summary of
  the listing (title, area, type, price, verified state) — the classic
  "summarize the retrieved document" RAG behaviour, still over DB rows only.
* No LLM is called anywhere; every claim maps to a Room field.

Privacy: only public listing fields are serialized (the same fields the
rooms list already exposes) plus cheap deterministic map intel (nearest
metro distance). No owner contact details, no fraud scores.
"""

from __future__ import annotations

import logging
from typing import Any

from rooms.models import Room

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Aspect detection — bilingual keyword sets (English + Bangla + Banglish)
# --------------------------------------------------------------------------

_ASPECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "price": (
        "price",
        "rent",
        "cost",
        "how much",
        "tk",
        "taka",
        "ভাড়া",
        "দাম",
        "কত",
        "কিরা",
        "বাজেট",
        "বিল",
        "bill",
    ),
    "area": (
        "area",
        "location",
        "where",
        "address",
        "ঠিকানা",
        "এলাকা",
        "জায়গা",
        "কোথায়",
        "কোন এলাকা",
    ),
    "room_type": (
        "type",
        "studio",
        "flat",
        "apartment",
        "room",
        "bedroom",
        "কেমন রুম",
        "রুম কেমন",
        "কী ধরনের",
        "কি ধরনের",
        "শয়নকক্ষ",
        "বাসা",
    ),
    "amenities": (
        "amenit",
        "wifi",
        "internet",
        "facilit",
        "what's included",
        "what is included",
        "সুবিধা",
        "কি আছে",
        "কী আছে",
        "ac",
        "furnished",
        "আসবাব",
        "পার্কিং",
        "parking",
        "জিম",
        "gym",
        "রান্নাঘর",
        "kitchen",
    ),
    "gender": (
        "gender",
        "male",
        "female",
        "boys",
        "girls",
        "family",
        "ছেলে",
        "মেয়ে",
        "লিঙ্গ",
        "পারিবারিক",
        "শুধু ছেলে",
        "শুধু মেয়ে",
    ),
    "size": (
        "size",
        "sqft",
        "square feet",
        "space",
        "big",
        "small",
        "large",
        "আয়তন",
        "কত বড়",
        "কত বড়ো",
        "বড়",
        "ছোট",
    ),
    "verified": (
        "verified",
        "verify",
        "genuine",
        "real",
        "ভেরিফাই",
        "নিরাপদ",
        "সত্যি",
        "আসল",
        "trust",
    ),
    "availability": (
        "available",
        "vacant",
        "free",
        "খালি",
        "এখন আছে",
        "আছে কি",
    ),
    "description": (
        "about",
        "describe",
        "summary",
        "details",
        "overview",
        "tell me",
        "কেমন",
        "বিস্তারিত",
        "বর্ণনা",
        "কথা বল",
        "সব",
    ),
    "photos": (
        "photo",
        "photos",
        "picture",
        "pictures",
        "image",
        "images",
        "look like",
        "looks like",
        "appearance",
        "ছবি",
        "কেমন দেখতে",
        "দেখতে কেমন",
        "দেখাও",
        "ছবিগুলো",
    ),
}

# Aspects we *cannot* answer from the listing — explicit refusal set so the
# Copilot never invents an answer ("what's the landlord like?" has no data).
_UNANSWERABLE = (
    "owner",
    "landlord",
    "মালিক",
    "landlord's",
    "phone",
    "contact",
    "মোবাইল",
    "নম্বর",
    "number",
    "negotiat",
    "দরদাম",
    "discount",
    "ছাড়",
    "credit",
    "loan",
    "ঋণ",
)

_PRICE_WORDS = ("price", "rent", "cost", "ভাড়া", "দাম", "কত", "কিরা", "bill", "বিল", "taka", "tk")


def _detect_aspect(message: str) -> str | None:
    lowered = message.lower().replace("।", " ")
    for word in _UNANSWERABLE:
        if word in lowered:
            return "unanswerable"
    hits = [
        aspect for aspect, words in _ASPECT_KEYWORDS.items() if any(w in lowered for w in words)
    ]
    if not hits:
        return None
    # Prefer the most specific aspect when several match; price wins when the
    # message is about money in any shape, and explicit photo words beat the
    # generic "কেমন/describe" fallback.
    if "price" in hits:
        return "price"
    if "amenities" in hits and any(w in lowered for w in _PRICE_WORDS):
        return "price"
    if "photos" in hits:
        return "photos"
    return hits[0]


# --------------------------------------------------------------------------
# Fact extraction — each answer line is derived from a real Room field
# --------------------------------------------------------------------------


def _fact_lines(room: Room) -> list[str]:
    lines = [f"{room.title} — {room.get_area_display()}"]
    lines.append(f"৳{int(room.price):,}/month ({room.get_room_type_display()})")
    if room.size_sqft:
        lines.append(f"{room.size_sqft} sqft")
    if room.gender_preference and room.gender_preference != "any":
        lines.append(f"Gender: {room.get_gender_preference_display()}")
    if room.amenities:
        lines.append("✓ " + ", ".join(str(a) for a in room.amenities))
    if room.verified:
        lines.append("✓ Identity-verified listing")
    if room.description:
        lines.append(room.description.strip()[:280])
    return lines


def _answer_price(room: Room, _message: str) -> str:
    text = f"{room.title} rents for ৳{int(room.price):,}/month."
    if room.amenities and any(
        str(a).lower() in ("utilities included", "bills included") for a in room.amenities
    ):
        text += " Utilities are included per the listing."
    return text


def _answer_area(room: Room, _message: str) -> str:
    return (
        f"This listing is in {room.get_area_display()}"
        + (f" ({room.address.strip()})" if room.address and len(room.address.strip()) < 120 else "")
        + "."
    )


def _answer_amenities(room: Room, _message: str) -> str:
    if not room.amenities:
        return "The listing doesn't mention any amenities."
    return "The listing includes: " + ", ".join(str(a) for a in room.amenities) + "."


def _answer_room_type(room: Room, _message: str) -> str:
    return f"It's a {room.get_room_type_display()}." + (
        f" {room.size_sqft} sqft." if room.size_sqft else ""
    )


def _answer_gender(room: Room, _message: str) -> str:
    if not room.gender_preference or room.gender_preference == "any":
        return "The listing is open to anyone (no gender preference)."
    return f"The listing is for {room.get_gender_preference_display()} only."


def _answer_size(room: Room, _message: str) -> str:
    if not room.size_sqft:
        return "The listing doesn't state the size."
    return f"It's {room.size_sqft} sqft."


def _answer_verified(room: Room, _message: str) -> str:
    if room.verified:
        return "Yes — this listing is identity-verified on Rentora."
    return "No — this listing isn't verified yet. Identity verification means the owner's NID was reviewed; it's not a quality guarantee."


def _answer_availability(room: Room, _message: str) -> str:
    return (
        "The listing is currently marked available."
        if room.is_available
        else "The listing is currently marked unavailable."
    )


def _answer_description(room: Room, _message: str) -> str:
    return room.description.strip() if room.description else "The listing has no description."


def _answer_photos(room: Room, _message: str) -> str:
    """Grounded answer from the listing's real photos (Tier 5).

    Uses deterministic pixel statistics (brightness / colourfulness / tones)
    and says plainly that this is a statistical description, not a claim
    about furniture or state.
    """
    from .image_profile import listing_image_profile

    profile = listing_image_profile(room)
    if not profile["available"] or profile["count"] == 0:
        return "This listing doesn't have any photos to describe yet."

    parts = [f"The listing has {profile['count']} photo(s)."]
    if profile["brightness"] and profile["colourfulness"]:
        parts.append(
            f"The main photo reads as {profile['brightness']} and {profile['colourfulness']}."
        )
    if profile["tones"]:
        parts.append("Dominant tones: " + ", ".join(dict.fromkeys(profile["tones"])) + ".")
    parts.append(
        "This is a statistical description of the photo (light and colour) — "
        "it can't tell you about furniture or condition."
    )
    return " ".join(parts)


_ASPECT_ANSWERS = {
    "price": _answer_price,
    "area": _answer_area,
    "amenities": _answer_amenities,
    "room_type": _answer_room_type,
    "gender": _answer_gender,
    "size": _answer_size,
    "verified": _answer_verified,
    "availability": _answer_availability,
    "description": _answer_description,
    "photos": _answer_photos,
}


def listing_answer(message: str, room: Room) -> dict[str, Any]:
    """Generate a grounded answer about ``room`` from ``message``.

    Returns a dict with ``text`` plus the aspect that was detected (or None
    for the summary fallback) so the UI can show a chip.
    """
    aspect = _detect_aspect(message)
    if aspect == "unanswerable":
        return {
            "text": (
                "I can only answer from this listing's details — that's not "
                "information the listing shows. You can message the owner from "
                "the room page for that."
            ),
            "aspect": None,
            "grounded": True,
        }
    if aspect in _ASPECT_ANSWERS:
        return {"text": _ASPECT_ANSWERS[aspect](room, message), "aspect": aspect, "grounded": True}

    # No aspect detected -> summarize the retrieved document (classic RAG).
    return {
        "text": "\n".join(_fact_lines(room)),
        "aspect": "summary",
        "grounded": True,
    }


def listing_facts(room: Room) -> dict[str, Any]:
    """The full grounded fact card for a listing (public fields only)."""
    metro = None
    try:
        from rooms.map_intel import nearest_metro_km

        distance = nearest_metro_km(room)
        if distance is not None:
            metro = round(float(distance), 2)
    except Exception:  # map intel must never break Copilot
        logger.debug("metro intel unavailable for room %s", room.pk, exc_info=True)

    return {
        "id": room.pk,
        "title": room.title,
        "price": float(room.price),
        "area": room.area,
        "area_display": room.get_area_display(),
        "room_type": room.room_type,
        "room_type_display": room.get_room_type_display(),
        "gender_preference": room.gender_preference,
        "size_sqft": room.size_sqft,
        "amenities": [str(a) for a in (room.amenities or [])],
        "verified": room.verified,
        "available": room.is_available,
        "address": room.address.strip() if room.address else "",
        "description": (room.description or "").strip(),
        "metro_km": metro,
        "image": (room.images.first().image.url if room.images.exists() else None),
    }


def listing_share_summary(room: Room) -> dict[str, Any]:
    """Compact, share-ready summary of a listing (Phase 13 — WhatsApp reach).

    Deterministic and grounded: built only from the listing's public fields
    (the same fields the rooms list exposes). Powers the WhatsApp "why this
    listing" share text so the share link opens pre-filled with real facts —
    nothing here is invented, and no owner contact details ever leak.
    """
    parts = [f"{room.title} — {room.get_area_display()}"]
    parts.append(f"৳{int(room.price):,}/month")
    if room.room_type:
        parts.append(room.get_room_type_display())
    if room.size_sqft:
        parts.append(f"{room.size_sqft} sqft")
    if room.amenities:
        parts.append("✓ " + ", ".join(str(a) for a in room.amenities[:4]))
    if room.verified:
        parts.append("✓ identity-verified listing")
    if not room.is_available:
        parts.append("currently unavailable")

    return {
        "id": room.pk,
        "title": room.title,
        "price": float(room.price),
        "area": room.area,
        "area_display": room.get_area_display(),
        "summary": " · ".join(parts),
    }
