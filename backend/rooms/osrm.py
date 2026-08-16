"""OSRM commute ETA (Tier 2).

Real road-network ETA for the map, backed by a self-hostable OSRM server.
By default it points at the free public demo server
(``https://router.project-osrm.org``); production should point
``OSRM_URL`` at a self-hosted instance (free, open-source, one Docker
command — Phase 8 docker work will cover that).

Design:
- **Cache-first**: identical coordinate pairs hit the Django cache for
  ``OSRM_CACHE_TTL`` (15 min), so repeated map renders never hammer the
  routing server and never pay the latency twice.
- **Graceful fallback**: any failure (timeout, 5xx, parse error, feature
  disabled) returns ``None`` and the caller falls back to the existing
  straight-line / MRT heuristics — the map never breaks because routing
  is down.
- **Mode mapping**: car → OSRM ``driving``; CNG and bus are *adjusted*
  driving profiles (congestion factors) and are honestly labelled as
  estimates — OSRM has no native cng/bus profile, so we never claim a
  precision we don't have.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Road modes → OSRM profile + an honest congestion adjustment. CNG and bus
# are slower than a private car in Dhaka traffic; the factors encode that.
MODE_PROFILES = {"car": "driving", "cng": "driving", "bus": "driving"}
MODE_FACTORS = {"car": 1.0, "cng": 1.2, "bus": 1.35}


def _setting(name: str, default):
    return getattr(settings, name, default)


def _http_get(url: str, timeout: float):
    """Thin seam so tests can patch the network call."""
    return requests.get(url, timeout=timeout)


def osrm_route(
    from_lat: float, from_lng: float, to_lat: float, to_lng: float, profile: str = "driving"
) -> dict | None:
    """Query OSRM for one route. Returns ``{"duration": s, "distance": m}``
    or ``None`` on any failure (never raises)."""
    if not _setting("OSRM_ENABLED", True):
        return None

    base = _setting("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
    cache_key = f"osrm:{profile}:{from_lat:.5f},{from_lng:.5f}:{to_lat:.5f},{to_lng:.5f}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    endpoint = (
        f"{base}/route/v1/{profile}/{from_lng},{from_lat};{to_lng},{to_lat}"
        "?overview=false&steps=false"
    )
    try:
        response = _http_get(endpoint, timeout=_setting("OSRM_TIMEOUT_SECONDS", 3))
        response.raise_for_status()
        route = response.json()["routes"][0]
        result = {"duration": float(route["duration"]), "distance": float(route["distance"])}
    except Exception as exc:  # network, HTTP, JSON — all the same: fall back
        logger.warning("OSRM route unavailable (%s); using heuristic fallback.", exc)
        return None

    cache.set(cache_key, result, _setting("OSRM_CACHE_TTL", 900))
    return result


def osrm_eta(
    from_lat: float, from_lng: float, to_lat: float, to_lng: float, mode: str = "car"
) -> dict | None:
    """Road ETA for one mode, or ``None`` when OSRM can't answer.

    Returns ``{"minutes", "distance_km", "source": "osrm", "mode"}``.
    """
    profile = MODE_PROFILES.get(mode, "driving")
    route = osrm_route(from_lat, from_lng, to_lat, to_lng, profile)
    if route is None:
        return None
    minutes = (route["duration"] / 60.0) * MODE_FACTORS.get(mode, 1.0)
    return {
        "minutes": round(minutes),
        "distance_km": round(route["distance"] / 1000.0, 2),
        "source": "osrm",
        "mode": mode,
    }
