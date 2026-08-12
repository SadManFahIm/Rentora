"""Hybrid search ranking (Phase 11+): neural + lexical + personalization.

The smart-search path used to rank with a single signal (TF-IDF/LSA cosine).
This module composes the ranking from three weighted signals, in priority
order that can never violate explicit user intent:

    Hard filters (NL budget/area/type/gender — applied by the caller)
        -> base relevance (neural embeddings blended with TF-IDF/LSA)
        -> personalization (only within the top of the relevant pool)
        -> secondary signals (tier/verified/newest — the view's ordering)

Every signal is optional and individually disable-able (settings flags), and
each has a graceful fallback: if embeddings are unavailable the blend reduces
to TF-IDF alone, and if that fails too the caller falls back to plain keyword
ordering — exactly the pre-existing behavior.
"""

from __future__ import annotations

import logging

from django.conf import settings

from . import embedding_service, semantic
from .models import Room

logger = logging.getLogger(__name__)

# Personalization may re-order *within* this many top-relevant rooms. Beyond
# it, base relevance decides — so a personalized-but-irrelevant room can
# never jump ahead of a genuinely relevant one that isn't in the top pool.
PERSONALIZATION_POOL = 40


def _normalize_leg(scored: list[tuple[int, float]] | None, room_ids: list[int]) -> dict[int, float]:
    """Clip negatives and normalize a scoring leg to [0, 1] for blending."""
    if not scored:
        return {}
    values = {room_id: max(float(score), 0.0) for room_id, score in scored if room_id in room_ids}
    if not values:
        return {}
    top = max(values.values())
    if top <= 0:
        return {room_id: 0.0 for room_id in values}
    return {room_id: score / top for room_id, score in values.items()}


def _base_score(sem: float, lex: float, has_sem: bool, has_lex: bool) -> float:
    """Weighted blend of the two relevance legs, renormalized when only one
    leg is available so the surviving signal isn't diluted by the missing one."""
    w_sem = float(getattr(settings, "SEMANTIC_SEARCH_WEIGHT", 0.7))
    w_lex = float(getattr(settings, "TFIDF_SEARCH_WEIGHT", 0.3))
    if has_sem and has_lex:
        total = w_sem + w_lex
        return (w_sem * sem + w_lex * lex) / total if total else 0.0
    if has_sem:
        return sem
    if has_lex:
        return lex
    return 0.0


def _load_pool_rooms(pool_ids: list[int]) -> list[Room]:
    """One batched fetch of the pool with exactly the columns the ranking
    signals read (profile vector + quality score) and images prefetched, so
    quality scoring never issues a per-room query."""
    return list(
        Room.objects.filter(id__in=pool_ids)
        .only(
            "id",
            "title",
            "description",
            "price",
            "area",
            "address",
            "lat",
            "lng",
            "room_type",
            "amenities",
            "gender_preference",
            "size_sqft",
        )
        .prefetch_related("images")
    )


def _personalization_scores(user, pool_ids: list[int]) -> dict[int, float] | None:
    """Reuse the recommendation engine's profile scoring for the pool."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if not getattr(settings, "PERSONALIZED_SEARCH_ENABLED", True):
        return None
    from recommendations.services.content_based import get_user_preference_scores

    rooms = _load_pool_rooms(pool_ids)
    if not rooms:
        return None
    return get_user_preference_scores(user, rooms)


def _quality_scores(pool_ids: list[int]) -> dict[int, float] | None:
    """0..1 listing-quality scores for the pool, one batched fetch + one
    MarketStat read (built once per ranking, never per room)."""
    if not getattr(settings, "LISTING_QUALITY_RANKING_ENABLED", True):
        return None
    rooms = _load_pool_rooms(pool_ids)
    if not rooms:
        return None
    from pricing.models import MarketStat

    market_stats = {(stat.area, stat.room_type): stat for stat in MarketStat.objects.all()}
    from .listing_quality import get_listing_quality

    return {
        room.id: min(get_listing_quality(room, market_stats)["score"] or 0, 100) / 100.0
        for room in rooms
    }


def _fraud_scores(pool_ids: list[int]) -> dict[int, float] | None:
    """0..1 risk for the pool from the EXISTING fraud engine (one query).

    FraudReport.score (0-100) is normalized; rooms without a report (or a
    clean report) get 0. Never hides a listing — only ranks it down.
    """
    if not getattr(settings, "FRAUD_AWARE_RANKING_ENABLED", True):
        return None
    from fraud.models import FraudReport

    rows = FraudReport.objects.filter(room_id__in=pool_ids, score__gt=0).values_list(
        "room_id", "score"
    )
    return {room_id: min(int(score), 100) / 100.0 for room_id, score in rows}


def hybrid_rank(
    query: str,
    pool_ids: list[int],
    user=None,
    *,
    top_k: int = 60,
    include_metadata: bool = False,
) -> dict | None:
    """Rank ``pool_ids`` by hybrid relevance (+ personalization).

    Returns ``{"ids": [...], "metadata": {room_id: {...}}}`` best-first, or
    None when no ranking signal is available at all (caller keeps default
    ordering). ``include_metadata`` exposes per-room scores — the view only
    turns it on for debug requests, never for normal users.
    """
    if not pool_ids:
        return {"ids": [], "metadata": {}}

    # Both legs are computed over the hard-filtered pool only, so semantic
    # similarity can never pull a room outside the requested budget/area in.
    lexical = semantic.semantic_rank(query, candidate_ids=pool_ids, top_k=len(pool_ids))
    neural = embedding_service.semantic_scores(query, candidate_ids=pool_ids, top_k=len(pool_ids))

    if not lexical and not neural:
        return None

    has_sem = bool(neural)
    has_lex = bool(lexical)
    sem_map = _normalize_leg(neural, pool_ids)
    lex_map = _normalize_leg(lexical, pool_ids)

    base: dict[int, float] = {}
    for room_id in pool_ids:
        base[room_id] = _base_score(
            sem_map.get(room_id, 0.0), lex_map.get(room_id, 0.0), has_sem, has_lex
        )

    order = sorted(base, key=base.get, reverse=True)

    pers_map: dict[int, float] | None = None
    if getattr(settings, "PERSONALIZED_SEARCH_ENABLED", True):
        pers_map = _personalization_scores(user, order[:PERSONALIZATION_POOL])

    final = dict(base)
    if pers_map:
        weight = float(getattr(settings, "PERSONALIZATION_WEIGHT", 0.15))
        for room_id in order[:PERSONALIZATION_POOL]:
            pers = pers_map.get(room_id, 0.0)
            final[room_id] = final[room_id] * (1.0 - weight) + pers * weight
        # Re-sort within the eligible pool, keep the rest in base order after.
        order = (
            sorted(order[:PERSONALIZATION_POOL], key=final.get, reverse=True)
            + order[PERSONALIZATION_POOL:]
        )

    # Secondary signals — applied only inside the top-relevant pool, so
    # quality can never lift an irrelevant room and fraud demotion always
    # yields to explicit relevance. Both are independently disable-able and
    # computed once per ranking call (batched, not per room).
    quality_map = _quality_scores(pool_ids)
    fraud_map = _fraud_scores(pool_ids)
    if quality_map or fraud_map:
        quality_weight = float(getattr(settings, "LISTING_QUALITY_RANKING_WEIGHT", 0.05))
        fraud_weight = float(getattr(settings, "FRAUD_RANKING_PENALTY_WEIGHT", 0.20))
        for room_id in order[:PERSONALIZATION_POOL]:
            if quality_map:
                q = quality_map.get(room_id, 0.5)
                final[room_id] = final[room_id] * (1.0 - quality_weight) + q * quality_weight
            if fraud_map:
                risk = fraud_map.get(room_id, 0.0)
                final[room_id] = max(final[room_id] - fraud_weight * risk, 0.0)
        order = (
            sorted(order[:PERSONALIZATION_POOL], key=final.get, reverse=True)
            + order[PERSONALIZATION_POOL:]
        )

    ids = order[:top_k]

    metadata = {}
    if include_metadata:
        for room_id in order:
            metadata[room_id] = {
                "semantic_score": round(sem_map.get(room_id, 0.0), 4),
                "lexical_score": round(lex_map.get(room_id, 0.0), 4),
                "personalization_score": (
                    round(pers_map.get(room_id, 0.0), 4) if pers_map else None
                ),
                "quality_score": round(quality_map.get(room_id, 0.0), 4) if quality_map else None,
                "fraud_risk": round(fraud_map.get(room_id, 0.0), 4) if fraud_map else None,
                "final_score": round(final[room_id], 4),
            }

    return {"ids": ids, "metadata": metadata}
