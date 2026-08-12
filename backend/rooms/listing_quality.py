"""Listing quality score - a transparent, rule-based 0-100 completeness score.

This is deliberately *not* a valuation and *not* a fraud score: it measures
how complete, useful and market-ready a listing is (photos, description
detail, amenities, address, price positioning). Every point is explainable —
the score is the weighted sum of six named category scores, and the
suggestions list tells the landlord exactly what to fix.

Reused by three surfaces:
- ``RoomDetailSerializer.listing_quality`` — tenants see a quality chip.
- Landlord dashboard insights — per-listing score + suggestions.
- Search ranking — a tiny secondary signal (never overrides relevance).

The pricing category reuses the existing price-insight engine (same market
snapshot the fraud engine reads), so quality, pricing and fraud all agree on
what \"normal\" is. All weights/levels are configurable in settings.
"""

from __future__ import annotations

from django.conf import settings

from .models import Room

# Amenities that materially help a tenant decide — used both in the amenities
# score and the \"add available amenities\" suggestion.
_KEY_AMENITIES = [
    "wifi",
    "attached bathroom",
    "kitchen",
    "furnished",
    "parking",
    "electricity",
    "gas",
    "ac",
]
# A description this long usually covers room size, facilities, rules, etc.
_GOOD_DESCRIPTION_LEN = 200
_MIN_DESCRIPTION_LEN = 80
# A title shorter than this is probably not informative.
_MIN_TITLE_LEN = 8
# Listings with this many photos are considered photo-complete.
_GOOD_PHOTO_COUNT = 4
_MIN_PHOTO_COUNT = 1
# A landmark within this many km makes the location instantly relatable.
_LANDMARK_RADIUS_KM = 3.0


def _quality_level(score: int, levels: list[tuple[int, str]]) -> str:
    for min_score, label in levels:
        if score >= min_score:
            return label
    return levels[-1][1]


def _pricing_subscore(room: Room, market_stats: dict | None) -> tuple[float, str | None]:
    """0..1 price-position score + optional suggestion, reusing price insight.

    No market data -> neutral 0.5 (never punish a listing for a thin market).
    Inside ±15% of the segment average -> full marks; further out -> partial.
    """
    if market_stats is None:
        return 0.5, None
    stat = market_stats.get((room.area, room.room_type))
    if stat is None or stat.sample_size < 3 or not stat.avg_price:
        return 0.5, None
    avg_price = float(stat.avg_price)
    price = float(room.price)
    if avg_price <= 0:
        return 0.5, None
    diff = (price - avg_price) / avg_price
    if abs(diff) <= 0.15:
        return 1.0, None
    if diff < 0:
        return 0.8, None  # below market — attractive, mild note
    return 0.5, "Your price is above the estimated market price for this area."


def get_listing_quality(
    room: Room,
    market_stats: dict | None = None,
) -> dict:
    """Compute the listing quality payload for ``room``.

    ``market_stats`` is an optional ``{(area, room_type): MarketStat}`` dict
    the caller built once (avoids one query per room on list/insight pages).
    Returns ``{score, level, category_scores, suggestions}`` — always a valid
    dict, never None, so callers can render it unconditionally.
    """
    if not getattr(settings, "LISTING_QUALITY_SCORE_ENABLED", True):
        return {"score": None, "level": None, "category_scores": {}, "suggestions": []}

    weights = getattr(settings, "LISTING_QUALITY_WEIGHTS", {})
    title = (room.title or "").strip()
    description = (room.description or "").strip()
    address = (room.address or "").strip()
    amenities = [str(a).strip().lower() for a in (room.amenities or [])]
    image_count = room.images.count() if hasattr(room, "images") else 0
    has_primary = (
        bool(room.images.filter(is_primary=True).exists()) if hasattr(room, "images") else False
    )
    price = float(room.price or 0)

    # ---- category subscores (0..1) ----
    basic_parts = [
        len(title) >= _MIN_TITLE_LEN,
        len(description) >= _MIN_DESCRIPTION_LEN,
        price > 0,
        bool(room.area),
        bool(room.room_type),
    ]
    basic = sum(basic_parts) / len(basic_parts)

    desc_len = len(description)
    if desc_len >= _GOOD_DESCRIPTION_LEN:
        description_score = 1.0
    elif desc_len >= _MIN_DESCRIPTION_LEN:
        description_score = 0.7
    elif desc_len > 0:
        description_score = 0.4
    else:
        description_score = 0.0

    if image_count >= _GOOD_PHOTO_COUNT:
        photo_score = 1.0
    elif image_count >= 2:
        photo_score = 0.75
    elif image_count == 1:
        photo_score = 0.5
    else:
        photo_score = 0.0
    if not has_primary and image_count > 0:
        photo_score = min(photo_score, 0.6)

    location_parts = [
        len(address) >= 15,
        bool(room.area),
        float(room.lat or 0) != 0 and float(room.lng or 0) != 0,
    ]
    # Nearby landmark (university/metro within a short walk) makes the
    # location instantly relatable — static computation, no queries.
    from .geo import haversine_km
    from .landmarks import ALL_LANDMARKS, Landmark

    nearby = any(
        haversine_km(float(room.lat), float(room.lng), lm.lat, lm.lng) <= _LANDMARK_RADIUS_KM
        for lm in ALL_LANDMARKS
        if isinstance(lm, Landmark)
    )
    location_parts.append(nearby)
    location = sum(location_parts) / len(location_parts)

    key_present = [a for a in _KEY_AMENITIES if a in amenities]
    if len(amenities) >= 6:
        amenity_score = 1.0
    elif len(amenities) >= 3:
        amenity_score = 0.75
    elif len(amenities) >= 1:
        amenity_score = 0.45
    else:
        amenity_score = 0.0
    amenity_score = min(amenity_score, 0.75 + 0.25 * (len(key_present) / len(_KEY_AMENITIES)))

    pricing_score, price_suggestion = _pricing_subscore(room, market_stats)

    category_scores = {
        "basic": round(basic, 3),
        "description": round(description_score, 3),
        "photos": round(photo_score, 3),
        "location": round(location, 3),
        "amenities": round(amenity_score, 3),
        "pricing": round(pricing_score, 3),
    }
    total = round(sum(weights.get(cat, 0) * score for cat, score in category_scores.items()), 1)
    level = _quality_level(total, getattr(settings, "LISTING_QUALITY_LEVELS", []))

    # ---- deterministic, actionable suggestions ----
    suggestions: list[str] = []
    if image_count < _GOOD_PHOTO_COUNT:
        suggestions.append(f"Add {_GOOD_PHOTO_COUNT - image_count} more photos.")
    if not has_primary and image_count > 0:
        suggestions.append("Set a primary photo so the card looks complete.")
    if desc_len < _GOOD_DESCRIPTION_LEN:
        suggestions.append(
            "Description is too short — add room size, facilities and nearby landmarks."
        )
    if not address or len(address) < 15:
        suggestions.append("Add a complete address or nearby landmark information.")
    missing_amenities = [a for a in _KEY_AMENITIES[:6] if a not in amenities]
    if missing_amenities:
        suggestions.append("Add available amenities: " + ", ".join(missing_amenities) + ".")
    if price_suggestion:
        suggestions.append(price_suggestion)

    return {
        "score": total,
        "level": level,
        "category_scores": category_scores,
        "suggestions": suggestions,
    }
