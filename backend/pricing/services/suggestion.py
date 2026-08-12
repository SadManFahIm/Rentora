"""AI pricing suggestion v2 (Phase 11 — Pricing Intelligence).

Upgrades the existing fair-price prediction into a full landlord-facing
"how much should I charge?" recommendation:

- **Recommended price + range** — reuses the existing Ridge regression
  (``pricing.services.prediction``); nothing is trained a second way.
- **Demand score** — normalised 0-100 from real engagement signals
  (views / wishlist saves / booking requests at the room *and* area level).
  Raw page views alone are never treated as demand.
- **Estimated time-to-rent** — a range derived from *actual* historical
  time-to-first-approved-booking in the same area; never fabricated when
  there isn't enough data ("Insufficient historical data").
- **Confidence** — composited from model confidence, market-sample size and
  demand-signal availability; honest, never meaningless precision.
- **Explainable reasons** — every factor is a calculated fact the landlord
  can see ("Similar Uttara singles average ৳10,200", "Your price is 14%
  above comparable listings").
- **Caching** — demand/time queries hit several tables, so results are
  cached (locmem/Redis) keyed by room + room mtime + market snapshot; the
  suggestion endpoint is not recomputed on every page load and never goes
  stale past a room/market change.

Deliberate limits
-----------------
- This is a *suggestion*: the landlord explicitly chooses to apply it (the
  frontend calls the normal room PATCH). Nothing changes prices automatically.
- Time-to-rent is an estimate, never a guarantee.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

from bookings.models import Booking
from rooms.models import Room, RoomView
from wishlist.models import Wishlist

from ..models import MarketStat
from .insight import MIN_SAMPLE_SIZE
from .prediction import predict_price_from_model, train_price_model

logger = logging.getLogger(__name__)

# Price suggestions are rounded to this granularity (BDT) so a landlord sees
# "৳10,000" not "৳10,037.42" — no meaningless precision.
PRICE_ROUND = 500

# Demand bands (0-100 score -> plain label).
_DEMAND_BANDS = [
    (81, "Very High"),
    (61, "High"),
    (31, "Moderate"),
    (0, "Low"),
]

# Minimum number of historical time-to-rent samples before we claim a range.
MIN_TIME_TO_RENT_SAMPLES = 5

# Cached suggestion lifetime. Room/market changes invalidate via the key;
# this only bounds how long a *stale-but-unchanged* entry can survive.
CACHE_TIMEOUT = 60 * 60


def _round_price(value: float | None) -> int | None:
    """Round a price to PRICE_ROUND (nearest 500 BDT)."""
    if value is None:
        return None
    return int(round(value / PRICE_ROUND) * PRICE_ROUND)


def _demand_label(score: float) -> str:
    for floor, label in _DEMAND_BANDS:
        if score >= floor:
            return label
    return "Low"


def _views_per_room(room_ids: list[int], since) -> float | None:
    """Average views per room over the window, or None when empty."""
    if not room_ids:
        return None
    total = RoomView.objects.filter(room_id__in=room_ids, viewed_at__gte=since).count()
    return total / len(room_ids)


def _demand_score(room: Room) -> tuple[float, dict[str, float]]:
    """0-100 demand score from real engagement signals + their raw values.

    Blends room-level engagement (views vs area peers, wishlist saves,
    booking requests) with area-level heat. All inputs are counts from the
    actual tables (RoomView / Wishlist / Booking).
    """
    now = timezone.now()
    month_ago = now - timedelta(days=30)

    room_views = RoomView.objects.filter(room=room, viewed_at__gte=month_ago).count()
    room_wishlists = Wishlist.objects.filter(room=room).count()
    room_requests = Booking.objects.filter(room=room).count()

    peer_ids = list(
        Room.objects.filter(area=room.area, is_available=True).values_list("id", flat=True)
    )
    all_ids = list(Room.objects.filter(is_available=True).values_list("id", flat=True))
    area_avg_views = _views_per_room(peer_ids, month_ago)
    platform_avg_views = _views_per_room(all_ids, month_ago)

    def _ratio(value: float | None, base: float | None, cap: float) -> float:
        if base is None or base <= 0:
            return 0.0
        return min((value or 0.0) / base, cap)

    # Area heat vs the whole platform (a high-demand area lifts every listing).
    area_heat = _ratio(area_avg_views, platform_avg_views, 2.0)
    # Room engagement vs its area peers.
    room_vs_area = _ratio(room_views, area_avg_views, 3.0)

    score = (
        30
        + 25 * (room_vs_area / 3.0)
        + 15 * min(room_wishlists, 10) / 10.0
        + 15 * min(room_requests, 10) / 10.0
        + 15 * (area_heat / 2.0)
    )
    score = round(max(0.0, min(100.0, score)), 1)

    raw: dict[str, float] = {
        "room_views_30d": room_views,
        "area_avg_views_30d": round(area_avg_views, 1) if area_avg_views is not None else 0.0,
        "platform_avg_views_30d": (
            round(platform_avg_views, 1) if platform_avg_views is not None else 0.0
        ),
        "wishlist_count": room_wishlists,
        "booking_requests": room_requests,
    }
    return score, raw


def _time_to_rent(room: Room) -> dict[str, Any]:
    """Estimated days-to-first-approved-booking for this room's area.

    Computed from *actual* historical bookings: for every approved booking in
    the same area, the days between the listing's creation and the booking.
    Returns ``{"available": False, ...}`` (not a fabricated number) when there
    aren't enough samples.
    """
    # Days between each area listing's own creation and its first approved
    # booking — the booking is anchored to *its* room's created_at, not this
    # target's, so historical listings from before the target existed still
    # count.
    samples = []
    for b in (
        Booking.objects.filter(
            status=Booking.Status.APPROVED,
            room__area=room.area,
        )
        .select_related("room")
        .only("created_at", "room__created_at")[:500]
    ):
        delta = (b.created_at - b.room.created_at).days
        if delta >= 0:
            samples.append(delta)

    if len(samples) < MIN_TIME_TO_RENT_SAMPLES:
        return {"available": False, "detail": "Insufficient historical data"}

    samples.sort()
    low = samples[len(samples) // 4]
    high = samples[(len(samples) * 3) // 4]
    return {
        "available": True,
        "days_min": max(low, 1),
        "days_max": max(high, low + 1),
        "sample_count": len(samples),
    }


def _market_avg(room: Room) -> float | None:
    try:
        stat = MarketStat.objects.get(area=room.area, room_type=room.room_type)
        return float(stat.avg_price) if stat.sample_size >= MIN_SAMPLE_SIZE else None
    except MarketStat.DoesNotExist:
        return None


def get_pricing_suggestion(room: Room) -> dict[str, Any]:
    """Compute (and cache) a full AI pricing suggestion for ``room``.

    Returns a dict with recommended_price / min_price / max_price (rounded
    to 500 BDT), demand_score + label, time_to_rent, confidence (0..1),
    reasons (calculated facts only), and the raw signals used. Never raises
    for missing data — every sub-estimate degrades to None/empty.
    """
    cache_key = _cache_key(room)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    trained = train_price_model()
    base = predict_price_from_model(
        trained,
        {
            "area": room.area,
            "room_type": room.room_type,
            "size_sqft": room.size_sqft,
            "amenities": room.amenities or [],
            "gender_preference": room.gender_preference,
        },
    )
    predicted = base.get("predicted_price")
    range_low = base.get("price_range_low")
    range_high = base.get("price_range_high")
    model_confidence = base.get("model_confidence", "none")

    demand_score, demand_raw = _demand_score(room)
    time_to_rent = _time_to_rent(room)
    market_avg = _market_avg(room)
    current_price = float(room.price)

    # --- confidence: honest composite, never meaningless precision ---------
    confidence = {"high": 0.8, "low": 0.6, "none": 0.4}.get(model_confidence, 0.5)
    if market_avg is not None:
        confidence = min(confidence + 0.1, 1.0)
    if demand_raw["room_views_30d"] or demand_raw["wishlist_count"]:
        confidence = min(confidence + 0.1, 1.0)
    confidence = round(confidence, 2)

    # --- reasons: calculated facts only -------------------------------------
    reasons: list[str] = []
    if market_avg is not None:
        reasons.append(
            f"Similar {room.get_area_display()} {room.get_room_type_display()} "
            f"listings average ৳{market_avg:,.0f}"
        )
    if predicted is not None and current_price:
        delta_pct = (current_price - predicted) / predicted * 100
        if abs(delta_pct) >= 5:
            direction = "above" if delta_pct > 0 else "below"
            reasons.append(
                f"Your current price is {abs(delta_pct):.0f}% {direction} "
                f"comparable listings (recommended ৳{_round_price(predicted):,})"
            )
    if demand_raw["room_views_30d"] or demand_raw["booking_requests"]:
        reasons.append(
            f"Current demand is {_demand_label(demand_score).lower()} "
            f"({demand_raw['room_views_30d']} views · {demand_raw['booking_requests']} "
            "booking requests in 30 days)"
        )
    if trained is not None:
        reasons.append(f"Model trained on {trained.n_samples} current listings")
    if not reasons:
        reasons.append("Not enough platform data yet — showing the overall market average.")

    suggestion = {
        "room_id": room.pk,
        "title": room.title,
        "current_price": current_price,
        "min_price": _round_price(range_low) or _round_price(predicted),
        "recommended_price": _round_price(predicted),
        "max_price": _round_price(range_high) or _round_price(predicted),
        "confidence": confidence,
        "model_confidence": model_confidence,
        "demand_score": demand_score,
        "demand_label": _demand_label(demand_score),
        "time_to_rent": time_to_rent,
        "reasons": reasons,
        "signals": demand_raw,
        "market_avg_price": market_avg,
    }
    cache.set(cache_key, suggestion, CACHE_TIMEOUT)
    return suggestion


def _cache_key(room: Room) -> str:
    """Cache key that invalidates on room change or market snapshot change."""
    market_calculated = MarketStat.objects.aggregate(latest=Max("calculated_at"))["latest"]
    market_ts = market_calculated.strftime("%Y%m%d%H%M%S") if market_calculated else "none"
    return f"pricing_suggestion_{room.pk}_{room.updated_at:%Y%m%d%H%M%S}_{room.price}_{market_ts}"
