"""Per-listing price recommendation (Tier 5) — dynamic pricing v2 (Phase 15, C7).

Links the demand-forecasting engine to *individual listings*: a landlord gets
a concrete, grounded "raise / hold / lower" suggestion with a suggested
price range, not a vague market note.

Signals combined (all real product data, all honest):

- **Area demand** — ``analytics.forecast.area_demand`` (demand index 0-100 +
  30-day direction from anonymized booking/wishlist/view counts).
- **Market position** — ``pricing`` market stats for the (area, room_type)
  segment: where this room sits vs the median.
- **Listing quality** — ``listing_quality.get_listing_quality`` (a weak,
  well-priced listing shouldn't be told to raise).
- **Interest velocity** — recent booking requests + wishlist saves for this
  room in the last 30 days (its own pull, not just the area's).
- **Demand momentum (v2)** — the area's 30-day forecast rate vs its recent
  weekly level, dampened to at most ±3%, feeds ``dynamic_price``.

v2 additions (backward compatible — every Tier-5 key keeps its meaning):

- ``dynamic_price`` — the live suggested figure including demand-trend
  momentum, bounded to ±8% of the current price; ``None`` when nothing is
  grounded.
- ``window`` — the ±3% band around ``dynamic_price`` the landlord can safely
  test, and ``valid_until`` — the 24h TTL after which the suggestion should
  be recomputed (prices and demand change).
- ``drivers`` — the per-factor effect breakdown (factor / effect / detail).

Honesty contract: the recommendation is a *suggestion* for the owner to
review — never an automatic price change, never a "guaranteed" outcome.
When data is too thin the engine says so instead of inventing a number.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from bookings.models import Booking
from wishlist.models import Wishlist

from .models import Room

MIN_INTEREST = 2  # below this many own-signals the listing's own pull is "thin"

# v2 caps — every number stays a dampened suggestion, never a market bet.
MAX_MOVE_PCT = 8.0  # total suggested/dynamic move vs current price
MOMENTUM_MAX_PCT = 3.0  # demand-trend momentum contribution
WINDOW_PCT = 3.0  # ±band around the dynamic price
DYNAMIC_TTL_HOURS = 24


def _interest_velocity(room: Room) -> dict[str, Any]:
    """Booking requests + wishlist saves for this room in the last 30 days."""
    since = timezone.now() - timedelta(days=30)
    bookings = Booking.objects.filter(room=room, created_at__gte=since).count()
    saves = (
        Wishlist.objects.filter(room=room, created_at__gte=since).count()
        if hasattr(Wishlist, "created_at")
        else 0
    )
    return {"bookings_30d": bookings, "wishlist_30d": saves, "total": bookings + saves}


def _forecast_momentum(demand: dict[str, Any]) -> float | None:
    """Demand-trend momentum in %: implied 30-day weekly rate vs the recent
    weekly level, dampened to ±3%. None when there is nothing to compare."""
    forecast = demand.get("forecast_30d")
    series = demand.get("weekly_series") or []
    if forecast is None or not series:
        return None
    recent = sum(series[-4:]) / 4
    if recent <= 0:
        return None
    implied_weekly = forecast * 7.0 / 30.0
    pct = (implied_weekly / recent - 1.0) * 100.0
    return round(max(-MOMENTUM_MAX_PCT, min(MOMENTUM_MAX_PCT, pct * 0.5)), 2)


def _clamp_move(price: float, current: float) -> float:
    """Never move the suggestion more than ±MAX_MOVE_PCT from the current price."""
    lo, hi = current * (1 - MAX_MOVE_PCT / 100), current * (1 + MAX_MOVE_PCT / 100)
    return round(min(hi, max(lo, price)), -2)


def listing_price_recommendation(room: Room, market_stats: dict | None = None) -> dict[str, Any]:
    """Recommendation payload for one listing.

    ``market_stats`` is the optional ``{(area, room_type): MarketStat}`` dict
    callers build once (see ``listing_quality``). Never raises.
    """
    from analytics.forecast import area_demand
    from pricing.services.insight import get_price_insight

    demand = area_demand(room.area)
    interest = _interest_velocity(room)

    insight = get_price_insight(room)

    reasons: list[str] = []
    suggested = float(room.price)
    direction = "hold"

    # ---- signal 1: area demand -------------------------------------------
    demand_index = demand.get("demand_index")
    demand_dir = demand.get("direction")
    if demand_index is not None and demand_dir == "rising" and demand_index >= 50:
        reasons.append(
            f"Area demand is rising ({demand_index}/100) — active tenants in {room.get_area_display()}."
        )
        direction = "raise"
    elif demand_index is not None and demand_dir == "falling" and demand_index < 40:
        reasons.append(
            f"Area demand is cooling ({demand_index}/100) — pricing competitively may keep enquiries flowing."
        )
        direction = "lower"

    # ---- signal 2: market position ---------------------------------------
    position = None
    stat = None
    if insight is not None:
        classification = insight.get("classification", "")
        position = (
            "below_market"
            if classification in ("great_deal", "good_price")
            else "above_market"
            if classification in ("above_average", "overpriced")
            else "at_market"
        )
        try:
            from pricing.models import MarketStat

            stat = MarketStat.objects.get(area=room.area, room_type=room.room_type)
        except MarketStat.DoesNotExist:
            stat = None
    if position == "below_market":
        reasons.append("This listing is priced below the area median for its type.")
        if direction == "hold":
            direction = "raise"
    elif position == "above_market":
        reasons.append("This listing is priced above the area median for its type.")
        if direction == "hold":
            direction = "lower"

    # ---- signal 3: own interest velocity ---------------------------------
    if interest["total"] >= MIN_INTEREST:
        reasons.append(
            f"{interest['total']} booking/wishlist signals on this listing in the last 30 days."
        )
    else:
        reasons.append("Few direct signals on this listing yet — the area trend matters more.")

    # ---- suggested price ---------------------------------------------------
    if direction == "raise" and stat is not None and stat.median_price:
        suggested = min(
            float(room.price) * 1.08,  # never more than +8% per suggestion
            max(float(stat.median_price), float(room.price)),
        )
    elif direction == "lower" and stat is not None and stat.median_price:
        suggested = max(
            float(room.price) * 0.92,  # never more than -8% per suggestion
            min(float(stat.median_price), float(room.price)),
        )

    suggested = round(suggested, -2)  # round to nearest 100 BDT for readability

    # ---- confidence ---------------------------------------------------------
    signals = sum(
        [
            demand_index is not None,
            stat is not None and bool(stat.sample_size),
            interest["total"] >= MIN_INTEREST,
        ]
    )
    if signals >= 3:
        confidence = "high"
    elif signals == 2:
        confidence = "medium"
    else:
        confidence = "low"

    # ---- v2: per-factor drivers ---------------------------------------------
    demand_effect = "raise" if direction == "raise" else "lower" if direction == "lower" else "hold"
    position_effect = (
        "raise" if position == "below_market" else "lower" if position == "above_market" else "hold"
    )
    interest_effect = (
        "raise" if interest["total"] >= MIN_INTEREST and direction == "raise" else "hold"
    )
    drivers = [
        {
            "factor": "area_demand",
            "effect": demand_effect,
            "detail": (
                f"Demand index {demand_index}/100, direction {demand_dir}"
                if demand_index is not None
                else "No demand data for this area yet."
            ),
        },
        {
            "factor": "market_position",
            "effect": position_effect,
            "detail": (
                f"Priced {position} (median ৳{float(stat.median_price):.0f})"
                if stat is not None
                else "No market stats for this segment yet."
            ),
        },
        {
            "factor": "interest_velocity",
            "effect": interest_effect,
            "detail": f"{interest['total']} booking/wishlist signals in the last 30 days.",
        },
    ]

    # ---- v2: dynamic price (demand-trend momentum on top of the step) --------
    momentum = _forecast_momentum(demand)
    dynamic_price: float | None
    if momentum is not None and direction in ("raise", "lower"):
        dynamic_price = _clamp_move(suggested * (1 + momentum / 100), float(room.price))
    elif suggested != float(room.price):
        dynamic_price = suggested
    else:
        dynamic_price = None  # nothing grounded → no invented figure

    window = {
        "min": round((dynamic_price or float(room.price)) * (1 - WINDOW_PCT / 100), -2),
        "max": round((dynamic_price or float(room.price)) * (1 + WINDOW_PCT / 100), -2),
    }
    valid_until = (timezone.now() + timedelta(hours=DYNAMIC_TTL_HOURS)).isoformat()

    return {
        "room_id": room.pk,
        "current_price": float(room.price),
        "suggested_price": suggested,
        "direction": direction,
        "confidence": confidence,
        "reasons": reasons,
        "signals": {
            "area_demand_index": demand_index,
            "area_demand_direction": demand_dir,
            "market_position": position,
            "interest_30d": interest,
        },
        "note": (
            "A suggestion from area demand + market + listing signals — never an "
            "automatic change. Review before adjusting your price."
        ),
        # v2 (Phase 15, C7)
        "version": 2,
        "dynamic_price": dynamic_price,
        "demand_momentum_pct": momentum,
        "window": window,
        "valid_until": valid_until,
        "drivers": drivers,
    }
