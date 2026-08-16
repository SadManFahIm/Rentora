"""Intelligent Rental Decision Map — map intelligence engine (Phase 7 v2).

Everything here is derived from **real data already in the platform**:

- **Area statistics** — average/median rent, listing counts, average size,
  availability, demand (views + wishlist saves + booking requests vs supply),
  price trend (``pricing.MarketStat``) and metro access (distance to the
  curated ``METRO_STATIONS`` set). Nothing is invented; areas with no data
  simply report nulls.
- **Commute ETA** — walking/driving are haversine x speed heuristics over
  straight-line distance (labelled ``mode`` and ``estimate: true`` — never
  presented as a turn-by-turn route). Transit mode interpolates the MRT Line-6
  corridor when *both* endpoints sit within 1.2 km of a metro station, and
  otherwise honestly reports that transit routing needs a routing provider.
- **Value score** (0-100) — transparent blend of price fit vs the area market,
  amenities, listing-quality score, KYC verification, demand and metro access.
  The weights live in settings so the formula is configurable and testable.
- **Affordability** — the *percentage of currently listed rooms* in each area
  that fit the user's budget. Not an arbitrary AI score.
- **Ideal areas** — ranks areas by budget fit + commute + availability + metro
  access and explains each recommendation with the same calculated facts.
- **Map NL search** — reuses ``rooms.nl_query.parse_nl_query`` (Bangla /
  English / Banglish) plus an amenity + metro-walk word table, and returns a
  structured intent the map can act on (filters + fly-to target + optional
  radius around a landmark/metro station).

Privacy: no private owner coordinates beyond the room's listing coordinate,
no internal fraud scores, no user history — demand is aggregate counts only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt
from statistics import median
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min, Q
from django.utils import timezone

from bookings.models import Booking
from pricing.models import MarketStat
from rooms.landmarks import METRO_STATIONS
from rooms.listing_quality import get_listing_quality
from rooms.models import Room, RoomView
from wishlist.models import Wishlist

from .nl_query import parse_nl_query

logger = logging.getLogger(__name__)

WALKING_SPEED_KMH = float(getattr(settings, "MAP_WALKING_SPEED_KMH", 4.8))
DRIVING_SPEED_KMH = float(getattr(settings, "MAP_DRIVING_SPEED_KMH", 24.0))
METRO_BOARDING_KM = float(getattr(settings, "MAP_METRO_BOARDING_KM", 1.2))
METRO_TRAIN_SPEED_KMH = float(getattr(settings, "MAP_METRO_TRAIN_SPEED_KMH", 33.0))
VALUE_WEIGHTS = {
    "price": float(getattr(settings, "MAP_VALUE_PRICE_WEIGHT", 0.30)),
    "amenities": float(getattr(settings, "MAP_VALUE_AMENITIES_WEIGHT", 0.20)),
    "quality": float(getattr(settings, "MAP_VALUE_QUALITY_WEIGHT", 0.15)),
    "verified": float(getattr(settings, "MAP_VALUE_VERIFIED_WEIGHT", 0.10)),
    "demand": float(getattr(settings, "MAP_VALUE_DEMAND_WEIGHT", 0.10)),
    "metro": float(getattr(settings, "MAP_VALUE_METRO_WEIGHT", 0.15)),
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def _nearest_metro(lat: float, lng: float) -> tuple[Any, float] | None:
    """(station, distance_km) to the nearest curated MRT station, or None."""
    best: tuple[Any, float] | None = None
    for station in METRO_STATIONS:
        d = haversine_km(lat, lng, station.lat, station.lng)
        if best is None or d < best[1]:
            best = (station, d)
    return best


def nearest_metro_km(room, return_station: bool = False):
    """Nearest metro distance for a room-like object (lat/lng attrs).

    Returns km, or (station, km) when ``return_station`` is set.
    """
    if room is None or room.lat is None or room.lng is None:
        return (None, None) if return_station else None
    nearest = _nearest_metro(float(room.lat), float(room.lng))
    if nearest is None:
        return (None, None) if return_station else None
    station, km = nearest
    return (station, km) if return_station else km


def metro_access_score(lat: float, lng: float) -> int:
    """0-100 transit-access score from walking time to the nearest station.

    <= 5 min walk -> 100; 15 min (1.2 km) -> 50; 30 min -> 0 (linear).
    """
    nearest = _nearest_metro(float(lat), float(lng))
    if nearest is None:
        return 0
    minutes = (nearest[1] / WALKING_SPEED_KMH) * 60
    return max(0, min(100, round(100 - (minutes / 30.0) * 100)))


@dataclass
class CommuteEstimate:
    mode: str
    minutes: int | None
    distance_km: float
    estimate: bool
    detail: str


def commute_eta(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    mode: str = "walking",
) -> CommuteEstimate:
    """ETA between two coordinates.

    ``mode`` in {walking, driving, transit}. Walking/driving are straight-line
    heuristics (distance / speed). Transit interpolates the MRT corridor when
    both ends are within ``METRO_BOARDING_KM`` of a station; otherwise returns
    ``minutes=None`` with an honest detail string.
    """
    distance = haversine_km(from_lat, from_lng, to_lat, to_lng)
    # Tier 2: road modes (driving/car/cng/bus) prefer a real road-network ETA
    # via OSRM when the server answers; any failure falls through to the
    # existing straight-line heuristic, so the map never breaks.
    if mode in ("driving", "car", "cng", "bus"):
        from .osrm import osrm_eta

        eta = osrm_eta(
            from_lat,
            from_lng,
            to_lat,
            to_lng,
            mode="car" if mode == "driving" else mode,
        )
        if eta is not None:
            return CommuteEstimate(
                mode=mode,
                minutes=eta["minutes"],
                distance_km=eta["distance_km"],
                estimate=True,
                detail=f"{mode.title()} ETA ~{eta['minutes']} min via road network (OSRM)",
            )
    if mode == "driving":
        minutes = round((distance / DRIVING_SPEED_KMH) * 60)
        return CommuteEstimate(
            mode="driving",
            minutes=minutes,
            distance_km=round(distance, 2),
            estimate=True,
            detail=f"Driving estimate ~{minutes} min ({distance:.1f} km straight line)",
        )
    if mode == "transit":
        a = _nearest_metro(from_lat, from_lng)
        b = _nearest_metro(to_lat, to_lng)
        if a and b and a[1] <= METRO_BOARDING_KM and b[1] <= METRO_BOARDING_KM:
            walk_min = round(((a[1] + b[1]) / WALKING_SPEED_KMH) * 60)
            ride_km = haversine_km(a[0].lat, a[0].lng, b[0].lat, b[0].lng)
            ride_min = round((ride_km / METRO_TRAIN_SPEED_KMH) * 60)
            return CommuteEstimate(
                mode="transit",
                minutes=walk_min + ride_min,
                distance_km=round(distance, 2),
                estimate=True,
                detail=f"MRT Line-6 estimate: {walk_min} min walking + {ride_min} min ride",
            )
        return CommuteEstimate(
            mode="transit",
            minutes=None,
            distance_km=round(distance, 2),
            estimate=False,
            detail="Transit routing unavailable for this pair (ends not near an MRT station). "
            "Try walking or driving.",
        )
    minutes = round((distance / WALKING_SPEED_KMH) * 60)
    return CommuteEstimate(
        mode="walking",
        minutes=minutes,
        distance_km=round(distance, 2),
        estimate=True,
        detail=f"Walking estimate ~{minutes} min ({distance:.1f} km straight line)",
    )


def _area_demand(area: str) -> dict[str, Any]:
    """Aggregate demand signals for an area (counts, not per-user history)."""
    room_ids = list(Room.objects.filter(area=area).values_list("id", flat=True))
    since = timezone.now() - timedelta(days=30)
    views = RoomView.objects.filter(room_id__in=room_ids, viewed_at__gte=since).count()
    saves = Wishlist.objects.filter(room_id__in=room_ids, created_at__gte=since).count()
    bookings = Booking.objects.filter(room_id__in=room_ids, created_at__gte=since).count()
    supply = max(len(room_ids), 1)
    # Weighted engagement per listing — a view is worth less than a save or a
    # booking request. Normalised to 0-100 with a soft cap at 20 engagements.
    raw = (views + saves * 3 + bookings * 6) / supply
    score = min(100, round((raw / 20.0) * 100))
    label = (
        "Very High"
        if score >= 81
        else "High"
        if score >= 61
        else "Moderate"
        if score >= 31
        else "Low"
    )
    return {
        "score": score,
        "label": label,
        "views_30d": views,
        "saves_30d": saves,
        "bookings_30d": bookings,
        "listings": len(room_ids),
    }


def area_statistics(area: str | None = None) -> list[dict[str, Any]]:
    """Aggregate stats per area (or one area when ``area`` is given)."""
    base = Room.objects.all()
    if area:
        base = base.filter(area__iexact=area)

    rows = (
        base.values("area")
        .annotate(
            count=Count("id"),
            available=Count("id", filter=Q(is_available=True)),
            avg_price=Avg("price"),
            avg_size=Avg("size_sqft"),
            min_price=Min("price"),
            max_price=Max("price"),
        )
        .order_by("-count")
    )

    out: list[dict[str, Any]] = []
    for row in rows:
        area_name = row["area"]
        prices = list(Room.objects.filter(area=area_name).values_list("price", flat=True))
        med = median(float(p) for p in prices) if prices else None
        demand = _area_demand(area_name)
        # Metro access: average of the visible rooms' scores.
        metro_scores = [
            metro_access_score(r.lat, r.lng)
            for r in Room.objects.filter(area=area_name).only("lat", "lng")[:200]
        ]
        avg_metro = round(sum(metro_scores) / len(metro_scores)) if metro_scores else None
        centre = _area_centre(area_name)
        out.append(
            {
                "area": area_name,
                "lat": centre[0] if centre else None,
                "lng": centre[1] if centre else None,
                "listings": row["count"],
                "available": row["available"],
                "avg_rent": round(float(row["avg_price"]), 2) if row["avg_price"] else None,
                "median_rent": round(med, 2) if med else None,
                "min_rent": float(row["min_price"]) if row["min_price"] else None,
                "max_rent": float(row["max_price"]) if row["max_price"] else None,
                "avg_size_sqft": round(row["avg_size"]) if row["avg_size"] else None,
                "demand": demand,
                "metro_access": avg_metro,
                "price_trend_pct": _price_trend(area_name),
            }
        )
    return out


def _price_trend(area: str) -> float | None:
    """% change between MarketStat avg and the current listing avg (or None)."""
    market = MarketStat.objects.filter(area__iexact=area).order_by("-calculated_at").first()
    if market is None:
        return None
    live = Room.objects.filter(area__iexact=area).aggregate(avg=Avg("price"))["avg"]
    if live is None or float(market.avg_price) == 0:
        return None
    return round(((float(live) - float(market.avg_price)) / float(market.avg_price)) * 100, 1)


def value_score(room: Room) -> dict[str, Any]:
    """0-100 transparent value score for a listing.

    Signals (all real data): price fit vs the area/type market, amenity
    richness, the listing-quality score, KYC verification, 30-day demand and
    metro access. The score is a weighted blend — see ``VALUE_WEIGHTS``.
    """
    stamp = (room.updated_at or room.created_at).timestamp()
    cache_key = f"map-value-{room.id}-{stamp}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 1. Price fit (0-100): how close to the area/type market median.
    market = MarketStat.objects.filter(area=room.area, room_type=room.room_type).first()
    ratio: float | None = None
    if market is not None and float(market.median_price) > 0:
        ratio = float(room.price) / float(market.median_price)
        price_fit = max(0.0, min(100.0, 100 - (ratio - 1.0) * 150))
    else:
        price_fit = 60.0  # no market baseline yet

    # 2. Amenities (0-100): 10 supported amenity slots.
    amenity_count = len(room.amenities or [])
    amenity_score = min(100.0, amenity_count * 14)

    # 3. Listing quality (0-100) from the existing quality engine.
    quality = get_listing_quality(room)
    quality_score = float(quality.get("score") or 50) if isinstance(quality, dict) else 50.0

    # 4. Verification (0 or 100).
    verified_score = 100.0 if room.verified else 0.0

    # 5. Demand (0-100) — 30-day area demand, plus a per-room boost when the
    #    room itself has recent views.
    area_demand = _area_demand(room.area)["score"]
    since = timezone.now() - timedelta(days=30)
    own_views = RoomView.objects.filter(room=room, viewed_at__gte=since).count()
    demand_score = min(100.0, area_demand + own_views * 2)

    # 6. Metro access (0-100).
    metro_score = float(metro_access_score(room.lat, room.lng))

    total = (
        price_fit * VALUE_WEIGHTS["price"]
        + amenity_score * VALUE_WEIGHTS["amenities"]
        + quality_score * VALUE_WEIGHTS["quality"]
        + verified_score * VALUE_WEIGHTS["verified"]
        + demand_score * VALUE_WEIGHTS["demand"]
        + metro_score * VALUE_WEIGHTS["metro"]
    )
    result = {
        "score": max(0, min(100, round(total))),
        "factors": {
            "price_fit": round(price_fit),
            "amenities": round(amenity_score),
            "quality": round(quality_score),
            "verified": verified_score,
            "demand": round(demand_score),
            "metro": round(metro_score),
        },
        "price_vs_market_pct": round((ratio - 1.0) * 100, 1) if ratio is not None else None,
    }
    cache.set(cache_key, result, timeout=60 * 15)
    return result


def affordability_stats(budget: float) -> list[dict[str, Any]]:
    """Percentage of currently listed rooms per area that fit ``budget``."""
    rows: list[dict[str, Any]] = []
    for area_row in Room.objects.values("area").annotate(total=Count("id")).order_by("area"):
        area = area_row["area"]
        total = area_row["total"]
        within = Room.objects.filter(area=area, price__lte=budget).count()
        centre = _area_centre(area)
        rows.append(
            {
                "area": area,
                "lat": centre[0] if centre else None,
                "lng": centre[1] if centre else None,
                "total": total,
                "within_budget": within,
                "percent": round((within / total) * 100) if total else 0,
            }
        )
    return rows


def _area_centre(area: str) -> tuple[float, float] | None:
    from .streets import area_center

    return area_center(area)


def _commute_to_area(area: str, lat: float, lng: float) -> CommuteEstimate | None:
    centre = _area_centre(area)
    if centre is None:
        return None
    return commute_eta(lat, lng, centre[0], centre[1], "transit")


def ideal_areas(
    budget: float,
    work_lat: float | None = None,
    work_lng: float | None = None,
    max_commute: int = 45,
    room_type: str | None = None,
) -> list[dict[str, Any]]:
    """Rank areas for the user and explain each recommendation.

    Score = affordability fit (40) + commute fit (30, when a destination is
    given) + availability (15) + metro access (15). Every reason cites the
    same calculated numbers — no subjective claims.
    """
    stats = area_statistics()
    aff_map = {a["area"]: a for a in affordability_stats(budget)}
    results: list[dict[str, Any]] = []
    for row in stats:
        if row["listings"] == 0:
            continue
        pct = aff_map.get(row["area"], {}).get("percent", 0)
        aff_score = min(100, pct * 1.2)
        reasons = [f"{pct}% of {row['area']} listings fit your ৳{budget:,.0f} budget"]
        commute_score = 75.0
        commute_minutes: int | None = None
        if work_lat is not None and work_lng is not None:
            eta = _commute_to_area(row["area"], work_lat, work_lng)
            if eta is not None and eta.minutes is not None:
                commute_minutes = eta.minutes
                commute_score = max(0, min(100, 100 - ((commute_minutes / max_commute) * 100)))
                reasons.append(f"~{commute_minutes} min commute to your destination (MRT estimate)")
            elif eta is not None:
                reasons.append("Commute not estimated — ends not near an MRT station")
            else:
                reasons.append("Commute not estimated — no area centre available")
        availability_score = (
            min(100, (row["available"] / row["listings"]) * 100) if row["listings"] else 0
        )
        metro_score = float(row["metro_access"] or 0)
        total = (
            aff_score * 0.40 + commute_score * 0.30 + availability_score * 0.15 + metro_score * 0.15
        )
        if room_type:
            room_count = Room.objects.filter(area=row["area"], room_type=room_type).count()
            if room_count == 0:
                continue
            reasons.append(f"{room_count} {room_type} listings available")
        centre = _area_centre(row["area"])
        results.append(
            {
                "area": row["area"],
                "lat": centre[0] if centre else None,
                "lng": centre[1] if centre else None,
                "score": round(total),
                "avg_rent": row["avg_rent"],
                "affordability_pct": pct,
                "commute_minutes": commute_minutes,
                "metro_access": row["metro_access"],
                "listings": row["listings"],
                "reasons": reasons,
            }
        )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:6]


AMENITY_WORDS: dict[str, str] = {
    "wifi": "WiFi",
    "wi-fi": "WiFi",
    "internet": "WiFi",
    "ac": "AC",
    "a/c": "AC",
    "এসি": "AC",
    "air condition": "AC",
    "furnished": "Furnished",
    "ফার্নিচার": "Furnished",
    "attached bath": "Attached Bath",
    "attached bathroom": "Attached Bath",
    "en suite": "Attached Bath",
    "parking": "Parking",
    "gym": "Gym",
    "kitchen": "Kitchen",
    "pet": "Pet Friendly",
    "pet friendly": "Pet Friendly",
    "পোষা": "Pet Friendly",
}

METRO_WORDS = ("metro", "মেট্রো", "mrt", "station", "স্টেশন")


def parse_map_query(text: str) -> dict[str, Any]:
    """Turn a free-text map query into a structured, map-actionable intent.

    Extends ``parse_nl_query`` (area/budget/type/gender) with amenities and a
    metro-walk constraint. Returns empty-safe fields; never raises.
    """
    intent = parse_nl_query(text)
    lowered = text.lower()
    amenities = []
    for word, canonical in AMENITY_WORDS.items():
        # Word-boundary match so "kache" doesn't hit "ac" — multi-word
        # phrases like "air condition" / "pet friendly" match as phrases.
        if re.search(rf"\b{re.escape(word)}\b", lowered) and canonical not in amenities:
            amenities.append(canonical)
    metro_walk = any(word in lowered for word in METRO_WORDS)
    return {
        **intent,
        "amenities": amenities,
        "metro_walk": metro_walk,
        "raw": text,
    }


def map_search_rooms(intent: dict[str, Any]) -> list[Room]:
    """Apply a parsed map intent to the room queryset (hard filters only)."""
    qs = Room.objects.filter(is_available=True)
    if intent.get("areas"):
        qs = qs.filter(area__in=intent["areas"])
    if intent.get("budget_max"):
        qs = qs.filter(price__lte=intent["budget_max"])
    if intent.get("room_type"):
        qs = qs.filter(room_type=intent["room_type"])
    if intent.get("gender"):
        qs = qs.filter(gender_preference=intent["gender"])
    results = list(qs[:200])
    # Amenity matching is done in Python (the JSON ``contains`` lookup is
    # Postgres-only; SQLite can't express it). 200 candidates is plenty for
    # a map viewport, and the intersection is exact + case-insensitive.
    wanted = [a.lower() for a in intent.get("amenities") or []]
    if wanted:
        results = [
            r
            for r in results
            if all(
                any(a.lower() in str(room_amenity).lower() for room_amenity in (r.amenities or []))
                for a in wanted
            )
        ]
    return results[:50]
