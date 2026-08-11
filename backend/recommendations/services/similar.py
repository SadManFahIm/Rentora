"""Similar-rooms: content-based nearest neighbours for one listing.

Reuses the exact 5-feature vector from ``content_based`` but instead of
scoring every room against a *user's* preference profile, it scores against
the *source room's* own features — so two listings that look alike (same
area, type, budget band, amenities) surface together. This powers the
"Similar rooms" carousel on the room detail/modal.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from rooms.models import Room

from .base import ScoredRoom

# The source room is its own ideal feature vector (all features match).
_SOURCE_VECTOR = np.ones(5)


def get_similar_rooms(room: Room, limit: int = 8, exclude_ids=()) -> list[ScoredRoom]:
    """Rank available rooms by feature similarity to ``room``.

    The source room is treated as the ideal vector: price is compared on a
    relative band (rooms within ±25% are a perfect price match, decaying to 0
    the further out), area/type/gender must match exactly, amenities are
    measured by Jaccard overlap. Rooms the source owner listed are excluded
    (a landlord's own duplicates aren't "similar rooms").
    """
    price = float(room.price)
    area = room.area
    room_type = room.room_type
    gender = room.gender_preference
    amenities = set(room.amenities or [])

    rooms = (
        Room.objects.filter(is_available=True)
        .exclude(pk=room.pk)
        .exclude(id__in=list(exclude_ids))
        .exclude(owner_id=room.owner_id)
    )

    scored: list[ScoredRoom] = []
    for candidate in rooms:
        candidate_price = float(candidate.price)
        price_fit = (
            1.0
            if abs(candidate_price - price) <= price * 0.25
            else max(1.0 - abs(candidate_price - price) / (price or 1), 0.0)
        )
        candidate_amenities = set(candidate.amenities or [])
        union = amenities | candidate_amenities
        amenity_overlap = len(amenities & candidate_amenities) / len(union) if union else 0.0

        vector = np.array(
            [
                price_fit,
                1.0 if candidate.area == area else 0.0,
                1.0 if candidate.room_type == room_type else 0.0,
                1.0 if candidate.gender_preference == gender else 0.0,
                amenity_overlap,
            ]
        )
        similarity = float(
            cosine_similarity(vector.reshape(1, -1), _SOURCE_VECTOR.reshape(1, -1))[0][0]
        )
        score = round(max(similarity, 0.0) * 100, 1)

        reasons = []
        if candidate.area == area:
            reasons.append(f"Same area: {area}")
        if candidate.room_type == room_type:
            reasons.append(f"Same type: {candidate.get_room_type_display()}")
        if price_fit >= 0.7:
            reasons.append("Similar price range")
        if amenity_overlap >= 0.4:
            reasons.append("Similar amenities")
        scored.append(ScoredRoom(room=candidate, score=score, reasons=reasons))

    scored.sort(key=lambda sr: sr.score, reverse=True)
    return scored[:limit]
