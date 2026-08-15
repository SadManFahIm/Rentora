"""Semantic search result cache (Tier-1 quick win).

The smart-search path (``rooms/?smart=1``) and Copilot both call
:func:`rooms.ranking.hybrid_rank`, whose expensive legs are the neural /
synonym embeddings plus the TF-IDF/LSA scoring — recomputed on *every*
request even when the exact same query over the exact same pool was just
answered.

This module caches the ranking result (the ordered id list) keyed by a hash
of (normalized query, sorted pool ids, top_k). Because the pool is the exact
set of rooms that passed the hard filters:

- a membership change (new / removed room) changes the key → cache miss;
- an identical repeat within the TTL hits the cache → same ordering, zero
  embedding work, same latency win for Copilot and the rooms list.

Two deliberate bypasses:

- **Authenticated (personalized) requests** — personalization re-ranks per
  user, so a shared cache would mix users. Anonymous search, the
  overwhelming majority of traffic on a public marketplace, gets the full
  benefit.
- **Debug requests (``include_metadata``)** — per-room score metadata must
  always be computed live.

Freshness: the ordering may lag a listing-quality / fraud-score change by at
most the TTL, which is the standard cache trade-off and is bounded by
``SEMANTIC_SEARCH_CACHE_TTL_SECONDS`` (default 15 minutes).
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache

from .ranking import hybrid_rank


def _cache_key(query: str, pool_ids: list[int], top_k: int) -> str:
    payload = f"{query.strip().lower()}|{top_k}|{','.join(map(str, sorted(set(pool_ids))))}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"semantic_rank:{digest}"


def cached_hybrid_rank(
    query: str,
    pool_ids: list[int],
    user=None,
    *,
    top_k: int = 60,
    include_metadata: bool = False,
) -> dict | None:
    """``hybrid_rank`` with a same-query cache.

    Returns the same shape as ``hybrid_rank`` (``{"ids": [...], "metadata": {}}``
    or None when no ranking signal is available). Bypasses the cache for
    personalized and debug-metadata requests and when
    ``SEMANTIC_SEARCH_CACHE_ENABLED`` is off.
    """
    use_cache = (
        getattr(settings, "SEMANTIC_SEARCH_CACHE_ENABLED", True)
        and not include_metadata
        and not (user is not None and getattr(user, "is_authenticated", False))
    )
    if not use_cache or not pool_ids:
        return hybrid_rank(
            query, pool_ids, user=user, top_k=top_k, include_metadata=include_metadata
        )

    key = _cache_key(query, pool_ids, top_k)
    cached_ids = cache.get(key)
    if cached_ids is not None:
        return {"ids": cached_ids, "metadata": {}}

    result = hybrid_rank(query, pool_ids, user=None, top_k=top_k, include_metadata=False)
    if result is None:
        return None
    ttl = int(getattr(settings, "SEMANTIC_SEARCH_CACHE_TTL_SECONDS", 900))
    cache.set(key, result["ids"], ttl)
    return result
