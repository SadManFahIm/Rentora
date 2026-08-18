"""Per-listing price recommendation (Tier 5).

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
    }
