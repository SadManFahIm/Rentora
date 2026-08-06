"""Combines content-based and collaborative scores into one ranked list.

Weighting is intentionally simple and fixed (60/40) rather than learned —
this is a rule-based system, not a model that needs tuning data.
"""

from __future__ import annotations

from ..models import UserActivity
from .base import ScoredRoom, popularity_fallback
from .collaborative import get_collaborative_recommendations
from .content_based import get_content_based_recommendations

CONTENT_WEIGHT = 0.6
COLLABORATIVE_WEIGHT = 0.4

# Pull a wider pool from each strategy than we ultimately return, so a room
# that's #1 collaboratively but outside the content-based top N (or vice
# versa) still gets a fair combined score instead of defaulting to 0.
CANDIDATE_POOL_MULTIPLIER = 3


def get_hybrid_recommendations(user, limit: int = 10) -> list[ScoredRoom]:
    has_activity = UserActivity.objects.filter(user=user).exists()
    if not has_activity:
        return popularity_fallback(limit)

    pool_size = limit * CANDIDATE_POOL_MULTIPLIER
    content_results = {
        sr.room.id: sr for sr in get_content_based_recommendations(user, limit=pool_size)
    }
    collaborative_results = {
        sr.room.id: sr for sr in get_collaborative_recommendations(user, limit=pool_size)
    }

    if not content_results and not collaborative_results:
        return popularity_fallback(limit)

    combined: dict[int, ScoredRoom] = {}

    for room_id, content_sr in content_results.items():
        collaborative_sr = collaborative_results.get(room_id)
        collaborative_score = collaborative_sr.score if collaborative_sr else 0.0
        combined_score = (
            content_sr.score * CONTENT_WEIGHT + collaborative_score * COLLABORATIVE_WEIGHT
        )
        reasons = list(content_sr.reasons)
        if collaborative_sr:
            reasons.extend(collaborative_sr.reasons)
        combined[room_id] = ScoredRoom(
            room=content_sr.room, score=round(combined_score, 1), reasons=reasons
        )

    for room_id, collaborative_sr in collaborative_results.items():
        if room_id in combined:
            continue
        combined_score = collaborative_sr.score * COLLABORATIVE_WEIGHT
        combined[room_id] = ScoredRoom(
            room=collaborative_sr.room,
            score=round(combined_score, 1),
            reasons=list(collaborative_sr.reasons),
        )

    ranked = sorted(combined.values(), key=lambda sr: sr.score, reverse=True)
    return ranked[:limit]
