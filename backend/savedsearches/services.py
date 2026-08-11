"""Matching logic for saved searches — shared by the API and the beat task.

The saved-search filters mirror the Rooms list endpoint params, so matching
reuses the same building blocks (django-filter style field lookups + the
portable full-text search from ``rooms.search``).
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from rooms.models import Room
from rooms.search import search_rooms

_ALLOWED_FILTERS = {
    "area": "area",
    "room_type": "room_type",
    "gender_preference": "gender_preference",
}


def apply_saved_filters(queryset, filters: dict[str, Any]):
    """Apply a saved search's filter dict to a Room queryset."""
    clause = Q()
    for key, field in _ALLOWED_FILTERS.items():
        value = filters.get(key)
        if value:
            clause &= Q(**{field: value})
    price_min = filters.get("price_min")
    price_max = filters.get("price_max")
    if price_min:
        clause &= Q(price__gte=price_min)
    if price_max:
        clause &= Q(price__lte=price_max)
    if filters.get("verified"):
        clause &= Q(verified=True)
    queryset = queryset.filter(clause)

    query_text = (filters.get("q") or "").strip()
    if query_text:
        queryset = search_rooms(queryset, query_text)
    return queryset


def find_new_matches(saved_search, queryset=None) -> list[Room]:
    """Rooms matching the saved search that arrived since the last check."""
    from django.utils import timezone

    queryset = queryset if queryset is not None else Room.objects.filter(is_available=True)
    queryset = apply_saved_filters(queryset, saved_search.filters)
    since = saved_search.last_checked_at or (timezone.now())
    if saved_search.last_checked_at is None:
        # First run: only brand-new rooms (created within the last day) alert.
        from datetime import timedelta

        since = timezone.now() - timedelta(days=1)
    return list(queryset.filter(created_at__gt=since).order_by("-created_at")[:10])
