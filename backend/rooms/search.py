"""Portable room full-text search (Phase 10 — Search v2).

Search must work on every environment the project runs in:

- **PostgreSQL (production)** — Django's ``SearchVector``/``SearchQuery`` give
  real full-text search with stemming and ranking; when the ``pg_trgm``
  extension is installed we also fold in fuzzy similarity so typos
  (``gulshan`` vs ``gulshun``) still match.
- **SQLite (local dev, CI)** — Postgres FTS functions don't exist, so we
  fall back to ``icontains`` across title/description/area.

The caller (RoomViewSet) decides when to apply search (``?q=`` present); this
module only turns a query string into an ordered queryset.
"""

from __future__ import annotations

import logging

from django.db import connection, models
from django.db.models import F, Func, Q

logger = logging.getLogger(__name__)

# Trigram similarity must clear this bar to count as a typo-tolerance match.
TRIGRAM_MIN_SIMILARITY = 0.25


class TrigramSimilarity(Func):
    """``similarity(a, b)`` from Postgres' pg_trgm extension."""

    function = "similarity"


def _fts_search(queryset: models.QuerySet, query: str) -> models.QuerySet:
    """Postgres full-text search, ranked. Requires SearchVector/SearchQuery."""
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

    vector = (
        SearchVector("title", weight="A")
        + SearchVector("area", weight="A")
        + SearchVector("description", weight="B")
    )
    search_query = SearchQuery(query)
    return (
        queryset.annotate(
            search_rank=SearchRank(vector, search_query),
            search_trigram=TrigramSimilarity(F("title"), query),
        )
        .filter(Q(search_rank__gt=0) | Q(search_trigram__gte=TRIGRAM_MIN_SIMILARITY))
        .order_by("-search_trigram", "-search_rank", "-created_at")
    )


def _icontains_search(queryset: models.QuerySet, query: str) -> models.QuerySet:
    """SQLite-safe fallback: every term must appear in title/area/description."""
    terms = [term for term in query.split() if term]
    if not terms:
        return queryset
    clause = Q()
    for term in terms:
        clause &= (
            Q(title__icontains=term) | Q(area__icontains=term) | Q(description__icontains=term)
        )
    return queryset.filter(clause)


def search_rooms(queryset: models.QuerySet, query: str) -> models.QuerySet:
    """Filter and rank ``queryset`` by relevance to ``query``.

    Strips query down to its searchable tokens, chooses the backend
    implementation, and gracefully degrades: if the Postgres-specific
    code path errors (e.g. pg_trgm extension missing), we fall back to
    ``icontains`` rather than fail the request.
    """
    query = (query or "").strip()
    if not query:
        return queryset

    if connection.vendor == "postgresql":
        try:
            return _fts_search(queryset, query)
        except Exception as exc:  # degrade instead of 500
            logger.warning("Postgres full-text search unavailable (%s); falling back", exc)

    return _icontains_search(queryset, query)
