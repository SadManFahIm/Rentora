"""Optional street-search fallback to OpenStreetMap's Nominatim geocoder.

The curated gazetteer in ``streets.py`` covers the major roads and districts a
tenant actually searches for, but not every lane in Dhaka. When a query misses
the gazetteer entirely, ``nominatim_search`` reaches out to the public OSM
Nominatim service so the map search box can still answer "Nawabpur Road" or
"Indira Road".

Nominatim's usage policy asks for a meaningful User-Agent and moderate
request rates — we send one, keep a tiny in-memory TTL cache, and treat every
network error as a miss (search should never fail because geocoding is down).
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Dhaka-centric viewbox (min_lon,min_lat,max_lon,max_lat) so "mirpur" can't
# match a city of the same name elsewhere in the world.
DHAKA_VIEWBOX = "90.28,23.65,90.50,23.92"
TIMEOUT_SECONDS = 4.0
CACHE_TTL_SECONDS = 3600  # street names change slowly; 1 hour is plenty

# Simple process-local TTL cache: {query: (fetched_at, results)}. Bounded to
# CACHE_MAX_ENTRIES (oldest evicted) so a long-lived server can't accumulate
# unbounded memory from many distinct autocomplete prefixes.
_CACHE: dict[str, tuple[float, list[dict]]] = {}
CACHE_MAX_ENTRIES = 256


def _cache_set(key: str, value: list[dict]) -> None:
    if len(_CACHE) >= CACHE_MAX_ENTRIES:
        # Drop the oldest entry (dicts preserve insertion order).
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (time.monotonic(), value)


def nominatim_search(query: str, limit: int = 5) -> list[dict]:
    """Geocode ``query`` via OSM Nominatim, Dhaka-biased.

    Returns a list of suggestions shaped like the gazetteer/landmark entries
    the geocode action already emits: ``{key, label, kind, lat, lng}``.
    Never raises — any failure (timeout, HTTP error, rate limit, malformed
    body) logs and returns an empty list.
    """
    q = query.strip()
    if not q:
        return []

    now = time.monotonic()
    cached = _CACHE.get(q)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    params = {
        "q": q,
        "format": "jsonv2",
        "limit": limit,
        "viewbox": DHAKA_VIEWBOX,
        "bounded": 1,
        "addressdetails": 0,
    }
    try:
        response = requests.get(
            NOMINATIM_URL,
            params=params,
            timeout=TIMEOUT_SECONDS,
            headers={
                "User-Agent": "RentRoomBD/1.0 (Dhaka room-rental map; contact: dev@rentora.bd)",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Nominatim search failed for %r: %s", q, exc)
        return []

    suggestions: list[dict] = []
    for row in payload[:limit]:
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        # Prefer the short display name; fall back to the full address.
        label = (row.get("name") or "").strip() or (row.get("display_name") or "").split(",")[0]
        suggestions.append(
            {
                "key": f"osm-{row.get('osm_type', 'node')}-{row.get('osm_id', '')}",
                "label": label,
                "kind": "street",
                "lat": float(lat),
                "lng": float(lon),
            }
        )

    _cache_set(q, suggestions)
    return suggestions
