"""Item-based collaborative filtering: "users who interacted with room X also
interacted with room Y" — built from the user-room interaction matrix implied
by UserActivity, with no notion of room content (price/area/amenities) at all.

Falls back to popularity ranking on cold start (too few users with any
activity yet for co-occurrence patterns to be meaningful).
"""

from __future__ import annotations

import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from rooms.models import Room

from ..models import UserActivity
from .base import ScoredRoom, popularity_fallback

# Below this many distinct users with logged activity, "similar user" patterns
# are too sparse/noisy to trust — fall back to popularity instead.
MIN_USERS_FOR_COLLABORATIVE = 5


def _build_interaction_matrix() -> pd.DataFrame | None:
    """user_id x room_id matrix of summed activity weight, or None if there
    isn't enough distinct-user activity to build a meaningful matrix."""
    rows = UserActivity.objects.filter(room__isnull=False).values("user_id", "room_id", "weight")
    if not rows:
        return None

    df = pd.DataFrame.from_records(rows)
    if df["user_id"].nunique() < MIN_USERS_FOR_COLLABORATIVE:
        return None

    interactions = df.groupby(["user_id", "room_id"], as_index=False)["weight"].sum()
    return interactions.pivot(index="user_id", columns="room_id", values="weight").fillna(0.0)


def get_collaborative_recommendations(user, limit: int = 10) -> list[ScoredRoom]:
    matrix = _build_interaction_matrix()
    if matrix is None or user.id not in matrix.index:
        return popularity_fallback(limit)

    room_ids = matrix.columns.tolist()
    # Item-item similarity: transpose so each room is a vector of the weights
    # every user gave it, then compare rooms to each other.
    room_similarity = cosine_similarity(matrix.T.values)
    similarity_df = pd.DataFrame(room_similarity, index=room_ids, columns=room_ids)

    user_row = matrix.loc[user.id]
    interacted_room_ids = user_row[user_row > 0].index.tolist()
    if not interacted_room_ids:
        return popularity_fallback(limit)

    # Score every room by how similar it is to the rooms this user already
    # engaged with, weighted by how strongly they engaged with each.
    scores = pd.Series(0.0, index=room_ids)
    for rid in interacted_room_ids:
        scores = scores.add(similarity_df[rid] * user_row[rid], fill_value=0.0)

    # Don't recommend rooms the user already interacted with.
    scores = scores.drop(index=interacted_room_ids, errors="ignore")

    available_ids = set(Room.objects.filter(is_available=True).values_list("id", flat=True))
    scores = scores[scores.index.isin(available_ids)]
    scores = scores[scores > 0]

    if scores.empty:
        return popularity_fallback(limit, exclude_ids=interacted_room_ids)

    max_score = scores.max()
    top = scores.sort_values(ascending=False).head(limit)

    rooms_by_id = {room.id: room for room in Room.objects.filter(id__in=top.index)}

    results = []
    for room_id, raw_score in top.items():
        room = rooms_by_id.get(room_id)
        if room is None:
            continue
        normalized = round(float(raw_score) / float(max_score) * 100, 1)
        results.append(
            ScoredRoom(
                room=room,
                score=normalized,
                reasons=["Popular with tenants who liked similar rooms"],
            )
        )

    return results
