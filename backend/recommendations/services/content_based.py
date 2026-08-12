"""Content-based recommendations: score rooms against a user's own preference
profile, built from their activity history.

Deliberately simple and explainable — a hand-built 5-feature vector per room
([price fit, area match, type match, amenities overlap, gender fit]) scored
against an "ideal" all-ones vector via cosine similarity, not a learned model.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from django.contrib.auth import get_user_model
from django.utils import timezone
from sklearn.metrics.pairwise import cosine_similarity

from rooms.models import Room

from ..models import UserActivity
from .base import ScoredRoom

User = get_user_model()

# Preference weight halves every RECENCY_HALF_LIFE_DAYS — older activity still
# counts, but a recent search/view says more about *current* intent than one
# from months ago.
RECENCY_HALF_LIFE_DAYS = 30

# The "ideal" feature vector every room is compared against — a room matching
# perfectly on all five dimensions would score a full 100%.
IDEAL_VECTOR = np.ones(5)


def build_user_preference_vector(user) -> dict[str, Any]:
    """Summarize what this user seems to want, from their activity history.

    Returns an empty dict if the user has no room-linked activity yet (the
    caller should treat that as "no preference data" and fall back).
    """
    activities = (
        UserActivity.objects.filter(user=user, room__isnull=False)
        .select_related("room")
        .order_by("-created_at")
    )

    area_scores: dict[str, float] = defaultdict(float)
    type_scores: dict[str, float] = defaultdict(float)
    amenity_scores: dict[str, float] = defaultdict(float)
    gender_scores: dict[str, float] = defaultdict(float)
    prices: list[float] = []
    price_weights: list[float] = []

    now = timezone.now()
    total_weight = 0.0

    for activity in activities:
        room = activity.room
        age_days = max((now - activity.created_at).total_seconds() / 86400, 0)
        recency_factor = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
        weight = activity.weight * recency_factor
        total_weight += weight

        area_scores[room.area] += weight
        type_scores[room.room_type] += weight
        gender_scores[room.gender_preference] += weight
        for amenity in room.amenities:
            amenity_scores[amenity] += weight
        prices.append(float(room.price))
        price_weights.append(weight)

    if not prices or total_weight == 0:
        return {}

    avg_price = float(np.average(prices, weights=price_weights))
    if len(prices) > 1:
        variance = float(np.average((np.array(prices) - avg_price) ** 2, weights=price_weights))
        std_price = variance**0.5
    else:
        std_price = avg_price * 0.2
    # A single data point (or a very tight cluster) would otherwise produce a
    # near-zero budget window that almost nothing can match.
    std_price = max(std_price, avg_price * 0.15, 1000.0)

    return {
        "preferred_area": max(area_scores, key=area_scores.get),
        "area_scores": dict(area_scores),
        "preferred_type": max(type_scores, key=type_scores.get),
        "type_scores": dict(type_scores),
        "preferred_gender": max(gender_scores, key=gender_scores.get),
        "avg_price": avg_price,
        "price_min": max(avg_price - std_price, 0.0),
        "price_max": avg_price + std_price,
        "amenity_scores": dict(amenity_scores),
        "top_amenities": {
            a for a, _ in sorted(amenity_scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
        },
    }


def _price_fit(room_price: float, prefs: dict) -> float:
    """1.0 if within the user's [price_min, price_max] band, decaying linearly
    to 0 the further outside it the room's price sits (one band-width out)."""
    price_min, price_max = prefs["price_min"], prefs["price_max"]
    if price_min <= room_price <= price_max:
        return 1.0
    band = max(price_max - price_min, 1.0)
    distance = (price_min - room_price) if room_price < price_min else (room_price - price_max)
    return max(1.0 - distance / band, 0.0)


def _gender_fit(user, room: Room) -> float:
    """How well a room's gender preference fits the user's own profile —
    `any` always fits; a same-gender-only room fits the user's own gender;
    an unset user gender is treated as a soft, partial (0.5) fit."""
    if room.gender_preference == Room.GenderPreference.ANY:
        return 1.0
    if not user.gender:
        return 0.5
    return 1.0 if user.gender == room.gender_preference else 0.0


def _build_room_vector(user, room: Room, prefs: dict) -> tuple[np.ndarray, list[str]]:
    price_fit = _price_fit(float(room.price), prefs)

    area_match = 1.0 if room.area == prefs["preferred_area"] else 0.0
    type_match = 1.0 if room.room_type == prefs["preferred_type"] else 0.0

    room_amenities = set(room.amenities or [])
    top_amenities = prefs["top_amenities"]
    amenities_overlap_ratio = (
        len(room_amenities & top_amenities) / len(top_amenities) if top_amenities else 0.0
    )

    gender_match = _gender_fit(user, room)

    vector = np.array([price_fit, area_match, type_match, amenities_overlap_ratio, gender_match])

    reasons = []
    if price_fit >= 0.7:
        reasons.append("Within your usual budget")
    if area_match:
        reasons.append(f"Preferred area: {room.area}")
    if type_match:
        reasons.append(f"Matches your preferred room type: {room.get_room_type_display()}")
    if amenities_overlap_ratio >= 0.3:
        shared = sorted(room_amenities & top_amenities)
        reasons.append(f"Has amenities you like: {', '.join(shared)}")
    if gender_match == 1.0 and room.gender_preference != Room.GenderPreference.ANY:
        reasons.append("Matches your gender preference")

    return vector, reasons


def get_user_preference_scores(user, rooms) -> dict[int, float] | None:
    """Per-room personalization score [0, 1] for an authenticated user.

    Reuses the exact same profile + feature vector as the recommendation
    engine (``build_user_preference_vector`` + ``_build_room_vector``) — the
    smart-search re-ranker calls this, so search and recommendations never
    drift apart. Returns None for cold-start users (no room-linked activity
    yet), which callers must treat as "no personalization".
    """
    prefs = build_user_preference_vector(user)
    if not prefs:
        return None
    ideal = IDEAL_VECTOR.reshape(1, -1)
    scores: dict[int, float] = {}
    for room in rooms:
        vector, _reasons = _build_room_vector(user, room, prefs)
        similarity = float(cosine_similarity(vector.reshape(1, -1), ideal)[0][0])
        scores[room.id] = round(max(similarity, 0.0), 4)
    return scores


def get_content_based_recommendations(user, limit: int = 10) -> list[ScoredRoom]:
    prefs = build_user_preference_vector(user)
    if not prefs:
        return []

    # Exclude rooms the user already interacted with (viewed, wishlisted,
    # booked, ...) — recommending a room they've already found and acted on
    # isn't useful, and collaborative filtering excludes the same set, so
    # this keeps the two strategies' candidate pools consistent.
    interacted_room_ids = UserActivity.objects.filter(user=user, room__isnull=False).values_list(
        "room_id", flat=True
    )
    rooms = (
        Room.objects.filter(is_available=True)
        .exclude(owner_id=user.id)
        .exclude(id__in=interacted_room_ids)
    )

    scored: list[ScoredRoom] = []
    ideal = IDEAL_VECTOR.reshape(1, -1)
    for room in rooms:
        vector, reasons = _build_room_vector(user, room, prefs)
        similarity = float(cosine_similarity(vector.reshape(1, -1), ideal)[0][0])
        score = round(max(similarity, 0.0) * 100, 1)
        scored.append(ScoredRoom(room=room, score=score, reasons=reasons))

    scored.sort(key=lambda sr: sr.score, reverse=True)
    return scored[:limit]
