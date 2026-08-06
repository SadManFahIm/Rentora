"""Geospatial helpers for room proximity and map queries.

Deliberately dependency-free — plain trigonometry, no PostGIS/GeoDjango — so
it runs identically on the SQLite dev database and a Postgres production one
(neither of which is assumed to have spatial extensions installed). Distances
use the haversine formula on WGS-84 lat/lng.

Radius queries do a cheap bounding-box pre-filter *in the database* (an
indexable lat/lng range) to discard the bulk of rows, then refine the
survivors with an exact per-row haversine in Python — so they stay fast as
the listing count grows, without needing a spatial index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .landmarks import Landmark

EARTH_RADIUS_KM = 6371.0088

# Degrees-per-kilometre conversions for building a bounding box around a point.
# Latitude degrees are ~constant; longitude degrees shrink toward the poles by
# cos(latitude), so that one is computed per-latitude by `lng_delta_for_km`.
_KM_PER_LAT_DEGREE = 110.574
_KM_PER_LNG_DEGREE_AT_EQUATOR = 111.320


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def lat_delta_for_km(km: float) -> float:
    """Latitude offset (degrees) that spans roughly `km` kilometres."""
    return km / _KM_PER_LAT_DEGREE


def lng_delta_for_km(km: float, at_lat: float) -> float:
    """Longitude offset (degrees) spanning ~`km` km at the given latitude."""
    denom = _KM_PER_LNG_DEGREE_AT_EQUATOR * math.cos(math.radians(at_lat))
    # Near the poles cos(lat)->0; clamp so we never divide by ~0. Dhaka is at
    # ~23.7°N so this guard is theoretical here, but it keeps the helper safe.
    return km / denom if abs(denom) > 1e-9 else 180.0


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float

    @classmethod
    def parse(cls, raw: str) -> BoundingBox:
        """Parse a `bbox` query value in GeoJSON order:
        ``minLng,minLat,maxLng,maxLat`` (i.e. west,south,east,north) — the
        same order `L.latLngBounds.toBBoxString()` produces on the frontend.

        Raises ValueError on anything malformed so the caller can turn it
        into a clean 400.
        """
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 4:
            raise ValueError(
                "bbox must be four comma-separated numbers: minLng,minLat,maxLng,maxLat"
            )
        try:
            min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
        except ValueError as exc:
            raise ValueError("bbox values must all be numbers") from exc
        if min_lat > max_lat or min_lng > max_lng:
            raise ValueError("bbox min values must not exceed max values")
        return cls(min_lat=min_lat, min_lng=min_lng, max_lat=max_lat, max_lng=max_lng)


def _measure(
    lat: float, lng: float, landmarks: tuple[Landmark, ...]
) -> list[tuple[Landmark, float]]:
    return [(lm, haversine_km(lat, lng, lm.lat, lm.lng)) for lm in landmarks]


def nearest_landmark(
    lat: float, lng: float, landmarks: tuple[Landmark, ...]
) -> tuple[Landmark, float] | None:
    """The single closest landmark to a point (with its distance in km), or
    None if `landmarks` is empty."""
    measured = _measure(lat, lng, landmarks)
    return min(measured, key=lambda pair: pair[1]) if measured else None


def landmarks_within(
    lat: float, lng: float, radius_km: float, landmarks: tuple[Landmark, ...]
) -> list[tuple[Landmark, float]]:
    """All landmarks within `radius_km` of a point, nearest first."""
    within = [pair for pair in _measure(lat, lng, landmarks) if pair[1] <= radius_km]
    return sorted(within, key=lambda pair: pair[1])
