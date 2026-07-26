"""Shared types and the popularity-based cold-start fallback used by every
recommendation strategy (content-based, collaborative, hybrid)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from django.db.models import Count

from rooms.models import Room


@dataclass
class ScoredRoom:
    room: Room
    score: float  # 0-100
    reasons: list[str] = field(default_factory=list)


def popularity_fallback(limit: int = 10, exclude_ids: Iterable[int] = ()) -> list[ScoredRoom]:
    """Rank rooms by wishlist count, booking count, and rating.

    Used whenever there isn't enough interaction data for a personalized
    score: a brand-new user (no activity at all) or too few users overall
    for collaborative filtering to mean anything.
    """
    rooms = (
        Room.objects.filter(is_available=True)
        .exclude(id__in=list(exclude_ids))
        .annotate(
            wishlist_count=Count("wishlisted_by", distinct=True),
            booking_count=Count("bookings", distinct=True),
        )
    )

    scored = []
    for room in rooms:
        raw = room.wishlist_count * 3 + room.booking_count * 5 + float(room.rating) * 2
        scored.append((room, raw))

    if not scored:
        return []

    max_raw = max(raw for _, raw in scored) or 1.0
    scored.sort(key=lambda pair: pair[1], reverse=True)

    results = []
    for room, raw in scored[:limit]:
        score = round(min(raw / max_raw, 1.0) * 100, 1)
        reasons = ["Popular with other tenants"]
        if room.wishlist_count > 0:
            reasons.append(f"Wishlisted by {room.wishlist_count} user(s)")
        if room.rating and float(room.rating) >= 4:
            reasons.append(f"Highly rated ({room.rating}★)")
        results.append(ScoredRoom(room=room, score=score, reasons=reasons))

    return results
