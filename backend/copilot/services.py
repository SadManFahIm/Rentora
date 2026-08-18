"""Rentora Copilot — conversational room discovery (Phase 11).

Hybrid by design:

    User message
        -> intent extraction (reuse rooms.nl_query + amenity/property words)
        -> existing search pipeline (hard filters -> hybrid semantic ranking)
        -> rule-based response generator over *retrieved* rows only

No LLM is required (and none is called): every listing claim in an answer
comes from actual database rows returned by the existing search engine, so
the Copilot **cannot hallucinate** a room, price or amenity. An optional
LLM layer is a future extension point only — and even then it would
summarise retrieved rows, never invent them.

Follow-up context: a ``session_id`` the client returns with each turn keys a
cache entry holding the accumulated structured filters. New messages merge
over the stored filters (a follow-up never forces the user to repeat prior
constraints), and "reset"/"clear" wipes the session.

Privacy: only public listing fields are ever serialized — no owner contact
details, no fraud scores, no internal data.
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, IntegerField, Value, When

from rooms.models import Room
from rooms.nl_query import parse_nl_query
from rooms.semantic_cache import cached_hybrid_rank

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Intent extraction
# --------------------------------------------------------------------------

# Amenity words (Bangla + English + Banglish) -> canonical amenity string.
_AMENITY_WORDS: dict[str, str] = {
    "wifi": "WiFi",
    "wi-fi": "WiFi",
    "wireless": "WiFi",
    "ইন্টারনেট": "WiFi",
    "ইন্টারনেট সংযোগ": "WiFi",
    "ac": "AC",
    "air conditioner": "AC",
    "এসি": "AC",
    "এয়ার কন্ডিশন": "AC",
    "furnished": "Furnished",
    "furniture": "Furnished",
    "আসবাবপত্র": "Furnished",
    "আসবাব": "Furnished",
    "parking": "Parking",
    "পার্কিং": "Parking",
    "attached bathroom": "Attached Bath",
    "attached bath": "Attached Bath",
    "attached washroom": "Attached Bath",
    "বাথরুম": "Attached Bath",
    "kitchen": "Kitchen",
    "রান্নাঘর": "Kitchen",
    "gym": "Gym",
    "জিম": "Gym",
    "pet friendly": "Pet Friendly",
    "pet": "Pet Friendly",
    "pets": "Pet Friendly",
    "পোষা": "Pet Friendly",
    "পোষা প্রাণী": "Pet Friendly",
    "elevator": "Elevator",
    "lift": "Elevator",
    "লিফট": "Elevator",
    "balcony": "Balcony",
    "বারান্দা": "Balcony",
    "garden": "Garden",
    "বাগান": "Garden",
    "water": "Water",
    "পানি": "Water",
    "গ্যাস": "Gas",
    "gas": "Gas",
}

# Property-type words (flat/apartment/hostel/sublet…) — these don't map to a
# Room field, so they only steer keyword/semantic relevance; they are never
# hard filters (a "flat" search can still surface a great studio).
_PROPERTY_WORDS = {
    "flat": "flat",
    "apartment": "apartment",
    "basa": "basa",
    "বাসা": "basa",
    "hostel": "hostel",
    "হোস্টেল": "hostel",
    "sublet": "sublet",
    "sub-let": "sublet",
    "mess": "mess",
    "মেস": "mess",
}

_RESET_PATTERNS = [
    r"\b(reset|clear|start over|new search)\b",
    r"\b(নতুন করে|আবার খুঁজি|রিসেট)\b",
]


def _extract_amenities(text: str) -> list[str]:
    """Amenity intent from free text (case-insensitive, Bangla-friendly)."""
    lowered = text.lower().replace("।", " ")
    found: list[str] = []
    for word, canonical in _AMENITY_WORDS.items():
        # word-boundary-ish match for latin; substring for Bangla is fine
        if word in lowered and canonical not in found:
            found.append(canonical)
    return found


def _extract_property_words(text: str) -> list[str]:
    lowered = text.lower()
    return [word for word in _PROPERTY_WORDS if word in lowered]


def _amenity_query_terms(amenities: list[str]) -> str:
    """Turn amenity intents into plain search terms for the semantic leg."""
    return " ".join(a.lower() for a in amenities)


def extract_intent(message: str) -> dict[str, Any]:
    """Structured intent from a free-text message (never raises).

    Returns a dict with the same keys the smart-search NL parser produces
    (budget_max / areas / room_type / gender / months) plus `amenities`,
    `property_words` and `hints`.
    """
    parsed = parse_nl_query(message)
    amenities = _extract_amenities(message)
    property_words = _extract_property_words(message)

    hints = list(parsed.get("hints") or [])
    if amenities:
        hints.append(" / ".join(amenities))
    if not hints:
        hints.append("keyword search")

    return {
        "budget_max": parsed.get("budget_max"),
        "areas": parsed.get("areas") or [],
        "room_type": parsed.get("room_type"),
        "gender": parsed.get("gender"),
        "months": parsed.get("months") or [],
        "amenities": amenities,
        "property_words": property_words,
        "hints": hints,
    }


def merge_intent(stored: dict | None, fresh: dict) -> dict:
    """Merge a new turn's intent over stored session filters.

    Fresh values win; stored values survive when the new message doesn't
    mention them (so a follow-up "শুধু furnished দেখাও" keeps area/budget).
    """
    base: dict = {
        "budget_max": None,
        "areas": [],
        "room_type": None,
        "gender": None,
        "months": [],
        "amenities": [],
        "property_words": [],
        "hints": [],
    }
    if stored:
        base.update(stored)
    for key in ("budget_max", "room_type", "gender"):
        if fresh.get(key) is not None:
            base[key] = fresh[key]
    for key in ("areas", "months", "amenities", "property_words", "hints"):
        if fresh.get(key):
            base[key] = fresh[key]
    return base


# --------------------------------------------------------------------------
# Session context
# --------------------------------------------------------------------------


def _session_key(session_id: str) -> str:
    return f"copilot_session_{session_id}"


def get_session(session_id: str | None) -> tuple[str, dict | None]:
    """Return ``(session_id, stored_intent)`` — minting an id when needed."""
    if session_id:
        stored = cache.get(_session_key(session_id))
        if stored is not None:
            return session_id, stored
    return (session_id or secrets.token_urlsafe(16)), None


def save_session(session_id: str, intent: dict) -> None:
    ttl = getattr(settings, "COPILOT_SESSION_TTL_SECONDS", 3600)
    cache.set(_session_key(session_id), intent, ttl)


def clear_session(session_id: str) -> None:
    cache.delete(_session_key(session_id))


def _is_reset(message: str) -> bool:
    lowered = message.strip().lower()
    return any(re.search(pattern, lowered) for pattern in _RESET_PATTERNS)


def _is_greeting(message: str) -> bool:
    lowered = message.strip().lower().rstrip("!?।")
    return lowered in {"hi", "hello", "hey", "হাই", "হ্যালো", "সালাম", "আসসালামু আলাইকুম"}


# --------------------------------------------------------------------------
# Retrieval — reuses the existing search pipeline
# --------------------------------------------------------------------------


def retrieve_rooms(intent: dict, user, top_k: int | None = None) -> tuple[list[Room], int, str]:
    """Query the existing room pipeline for ``intent``.

    Returns ``(rooms, total_count, kind)`` where kind is ``"match"`` or
    ``"none"``. Hard filters always gate first (budget/area/type/gender/
    amenities) — a ৳10,000 budget can never be "discovered" past. The
    surviving pool is ranked with the existing hybrid (semantic + lexical +
    personalization + quality + fraud) ranking.
    """
    top_k = top_k or getattr(settings, "COPILOT_MAX_RESULTS", 5)

    qs = Room.objects.filter(is_available=True).select_related("owner")
    if intent.get("areas"):
        qs = qs.filter(area__in=intent["areas"])
    if intent.get("budget_max"):
        qs = qs.filter(price__lte=intent["budget_max"])
    if intent.get("room_type"):
        qs = qs.filter(room_type=intent["room_type"])
    if intent.get("gender"):
        qs = qs.filter(gender_preference__in=[intent["gender"], "any"])
    amenities = intent.get("amenities") or []
    for amenity in amenities:
        qs = qs.filter(amenities__icontains=amenity)

    pool_ids = list(qs.values_list("id", flat=True))
    if not pool_ids:
        return [], 0, "none"

    query = " ".join(
        part
        for part in [
            intent.get("query_text", ""),
            _amenity_query_terms(amenities),
            " ".join(intent.get("property_words") or []),
        ]
        if part
    ).strip()

    ranked = None
    if query:
        # Same-query cache (Tier-1 quick win): Copilot is public and often
        # repeats queries — reuse the last ranking over the same pool.
        ranked = cached_hybrid_rank(query, pool_ids, user=user, top_k=len(pool_ids))
    if ranked and ranked["ids"]:
        ordering = Case(
            *[
                When(pk=room_id, then=Value(position))
                for position, room_id in enumerate(ranked["ids"])
            ],
            output_field=IntegerField(),
        )
        rooms = list(qs.filter(pk__in=ranked["ids"]).order_by(ordering)[:top_k])
    else:
        rooms = list(qs.order_by("-created_at")[:top_k])

    return rooms, len(pool_ids), "match"


# --------------------------------------------------------------------------
# Response generation — rule-based, every claim backed by retrieved rows
# --------------------------------------------------------------------------


def _room_line(room: Room, index: int) -> str:
    amenities = ", ".join(str(a) for a in (room.amenities or [])[:4])
    line = f"{index}. {room.title} — {room.get_area_display()} — ৳{int(room.price):,}/mo"
    if room.room_type:
        line += f" ({room.get_room_type_display()})"
    if amenities:
        line += f"\n   ✓ {amenities}"
    return line


def build_suggestions(intent: dict, room_count: int) -> list[str]:
    """Next-step suggestions derived from the current intent (no guesses)."""
    suggestions: list[str] = []
    amenities = intent.get("amenities") or []
    if "Furnished" not in amenities and room_count > 0:
        suggestions.append("শুধু furnished দেখাও")
    if room_count > 0:
        suggestions.append("দাম অনুযায়ী সাজাও")
    if room_count > 3:
        suggestions.append("আরও রুম দেখাও")
    if not suggestions:
        suggestions.append("budget বাড়িয়ে দেখি")
        suggestions.append("অন্য এলাকায় খুঁজি")
    return suggestions[:3]


def _no_match_message(intent: dict) -> str:
    parts = []
    if intent.get("areas"):
        parts.append(intent["areas"][0])
    if intent.get("budget_max"):
        parts.append(f"৳{intent['budget_max']:,} এর মধ্যে")
    return (
        "I couldn't find a listing that matches all your criteria"
        + (f" ({', '.join(parts)})" if parts else "")
        + ". Try raising the budget or choosing another area — or tell me to "
        "relax a filter."
    )


def generate_response(
    message: str,
    intent: dict,
    rooms: list[Room],
    total_count: int,
) -> dict[str, Any]:
    """Rule-based answer. The only 'intelligence' is the retrieval itself —
    this never asserts anything not present in ``rooms``."""
    if total_count == 0:
        text = _no_match_message(intent)
    elif len(rooms) == 1:
        room = rooms[0]
        text = f"I found 1 matching room in {room.get_area_display()}."
    else:
        area_bits = [a for a in (intent.get("areas") or [])]
        budget = intent.get("budget_max")
        where_parts = [
            p
            for p in [area_bits[0] if area_bits else None, f"under ৳{budget:,}" if budget else None]
            if p
        ]
        where = " · ".join(where_parts)
        text = f"I found {total_count} matching rooms" + (f" in {where}" if where else "") + "."
        if len(rooms) < total_count:
            text += f" Showing the top {len(rooms)}."

    lines = "\n".join(_room_line(room, i) for i, room in enumerate(rooms, 1))
    full = text
    if lines:
        full += "\n\n" + lines
    return {
        "message": full,
        "intent": intent,
        "listings": [
            {
                "id": room.pk,
                "title": room.title,
                "price": float(room.price),
                "area": room.area,
                "room_type": room.room_type,
                "amenities": [str(a) for a in (room.amenities or [])],
                "verified": room.verified,
                "tier": room.tier,
                "image": (room.images.first().image.url if room.images.exists() else None),
            }
            for room in rooms
        ],
        "total_count": total_count,
        "suggestions": build_suggestions(intent, total_count),
    }


# --------------------------------------------------------------------------
# Listing mode (Tier 3 — RAG Copilot)
# --------------------------------------------------------------------------

_LISTING_SUGGESTIONS = [
    "দাম কত?",
    "কি সুবিধা আছে?",
    "কোথায় অবস্থিত?",
    "ভেরিফাইড কি?",
]


def _empty_listing_turn(session_id: str | None, message: str) -> dict[str, Any]:
    """Graceful fallback for a listing that no longer exists — never 500."""
    return {
        "session_id": session_id or "",
        "message": (
            "I couldn't find that listing — it may have been taken down or is "
            "no longer available. You can search for other rooms instead."
        ),
        "intent": extract_intent(""),
        "listings": [],
        "total_count": 0,
        "suggestions": ["আবার খুঁজি"],
        "mode": "listing",
        "listing": None,
    }


def _listing_turn(message: str, listing_id: int, session_id: str | None) -> dict[str, Any]:
    """One Copilot turn grounded on a *single* listing (RAG over one doc).

    The retrieval step is the listing row itself; the answer is generated
    strictly from its public fields (``listing_qa.listing_answer``). Follow-up
    turns keep working because the client re-sends the same ``listing_id`` —
    search filters never leak into listing mode.
    """
    from .listing_qa import listing_answer, listing_facts

    try:
        room = Room.objects.filter(pk=listing_id, is_available=True).select_related("owner").first()
    except (ValueError, TypeError):
        room = None
    if room is None:
        return _empty_listing_turn(session_id, message)

    answer = listing_answer(message, room)
    return {
        "session_id": session_id or "",
        "message": answer["text"],
        "intent": extract_intent(""),
        "listings": [],
        "total_count": 0,
        "suggestions": _LISTING_SUGGESTIONS,
        "mode": "listing",
        "listing": listing_facts(room),
        "aspect": answer["aspect"],
    }


def listing_facts_for(room_id: int) -> dict[str, Any] | None:
    """Public grounded fact card for one listing (used by the GET endpoint)."""
    from .listing_qa import listing_facts

    try:
        room = Room.objects.filter(pk=room_id, is_available=True).select_related("owner").first()
    except (ValueError, TypeError):
        return None
    if room is None:
        return None
    return listing_facts(room)


def share_summary_for(room_id: int) -> dict[str, Any] | None:
    """Share-ready, deterministic summary for one listing (Phase 13).

    Powers the WhatsApp share text pre-fill. None when the listing is missing
    or unavailable (matching the fact-card endpoint's 404 behaviour).
    """
    from .listing_qa import listing_share_summary

    try:
        room = Room.objects.filter(pk=room_id, is_available=True).select_related("owner").first()
    except (ValueError, TypeError):
        return None
    if room is None:
        return None
    return listing_share_summary(room)


def chat(
    message: str,
    session_id: str | None,
    user,
    listing_id: int | None = None,
) -> dict[str, Any]:
    """Full Copilot turn: session -> intent -> retrieve -> respond.

    When ``listing_id`` is given the turn is **grounded on that one listing**
    (RAG over a single document) instead of a search — see ``_listing_turn``.
    """
    if listing_id is not None:
        return _listing_turn(message or "", listing_id, session_id)

    message = (message or "").strip()
    if not message:
        return {
            "session_id": session_id or "",
            "message": "What are you looking for? Try: “Uttara-তে ১০ হাজারের মধ্যে furnished student room”.",
            "intent": extract_intent(""),
            "listings": [],
            "total_count": 0,
            "suggestions": [],
            "mode": "search",
            "listing": None,
            "aspect": None,
        }

    sid, stored = get_session(session_id)

    if _is_reset(message):
        clear_session(sid)
        return {
            "session_id": sid,
            "message": "Starting a fresh search — what are you looking for?",
            "intent": extract_intent(""),
            "listings": [],
            "total_count": 0,
            "suggestions": [],
            "mode": "search",
            "listing": None,
            "aspect": None,
        }

    if _is_greeting(message):
        return {
            "session_id": sid,
            "message": (
                "Hi! I'm Rentora Copilot. Ask me for rooms in natural language — "
                "e.g. “Uttara-তে ১০ হাজারের মধ্যে student room চাই” or "
                "“furnished studio in Dhanmondi under 15k”. I search the live "
                "listings, so every room I show actually exists."
            ),
            "intent": extract_intent(""),
            "listings": [],
            "total_count": 0,
            "suggestions": [
                "Uttara-তে ১০ হাজারের মধ্যে room",
                "Dhanmondi-তে furnished studio",
                "Mirpur-এ single room, AC",
            ],
            "mode": "search",
            "listing": None,
            "aspect": None,
        }

    fresh = extract_intent(message)
    intent = merge_intent(stored, fresh)
    intent["query_text"] = message

    rooms, total_count, kind = retrieve_rooms(intent, user)
    response = generate_response(message, intent, rooms, total_count)
    response["session_id"] = sid
    response["mode"] = "search"
    response["listing"] = None
    response["aspect"] = None

    if kind == "match":
        save_session(sid, intent)
    else:
        # Keep the stored intent for a possible relaxed follow-up, but the
        # failed filters are already visible in the answer.
        save_session(sid, intent)
    return response
