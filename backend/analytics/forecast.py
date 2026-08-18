"""Demand forecasting (Tier 4) — per-area demand index + 30-day trend.

Deterministic, self-hosted, privacy-lean: demand is estimated from **counts**
of real product signals — booking requests, approved bookings, wishlist
saves and listing views — never from individual user data. All counts are
anonymous aggregates (``analytics.Event`` rows are already PII-free by
contract).

Method: for each area, weekly counts over the last 12 weeks are turned into
a ``demand_index`` (0-100, scaled against the area's own historical peak so
it reads as "how hot is this area right now") and a naive linear-trend
forecast for the next 30 days. When an area has no history the index is
``None`` with an honest note — the API never fabricates demand.

This powers the landlord view ("is demand rising in Uttara?") and the admin
Trust & Safety / growth dashboard.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from bookings.models import Booking
from rooms.models import Room
from wishlist.models import Wishlist

from .models import Event

LOOKBACK_WEEKS = 12
FORECAST_DAYS = 30
MIN_SIGNAL = 3  # below this total signal count the area is "insufficient data"


def _weekly_series(area: str, weeks: int = LOOKBACK_WEEKS) -> list[int]:
    """Weekly total-signal counts (booking requests + wishlist saves + views)
    for ``area`` over the last ``weeks`` weeks, oldest first."""
    now = timezone.now()
    series: list[int] = []
    for w in range(weeks - 1, -1, -1):
        start = now - timedelta(weeks=w + 1)
        end = now - timedelta(weeks=w)
        n = 0
        # Wishlist saves (public interest signal)
        n += (
            Wishlist.objects.filter(
                room__area=area, created_at__gte=start, created_at__lt=end
            ).count()
            if hasattr(Wishlist, "created_at")
            else 0
        )
        # Booking requests + approvals
        n += Booking.objects.filter(
            room__area=area, created_at__gte=start, created_at__lt=end
        ).count()
        # Analytics events (views / booking_requested tracked by the frontend)
        n += (
            Event.objects.filter(
                event__in=("booking_requested", "room_view"),
                properties__room_id__isnull=False,
                created_at__gte=start,
                created_at__lt=end,
            )
            .filter(Q(properties__area=area) | Q(path__icontains=area.lower()))
            .count()
        )
        series.append(n)
    return series


def _linear_trend(series: list[int], forecast_days: int = FORECAST_DAYS) -> dict[str, Any]:
    """Naive least-squares trend over weekly counts.

    Returns the slope in "signals per week", the implied 30-day forecast
    total, and direction (rising/falling/flat) — with the honest caveat that
    this is a simple trend, not a seasonal model.
    """
    n = len(series)
    if n < 2:
        return {"slope": None, "forecast_30d": None, "direction": "insufficient"}

    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = (
        (sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series, strict=True)) / denom)
        if denom
        else 0.0
    )

    # Extrapolate the last week's level forward by forecast_days/7 weeks.
    last_level = mean_y + slope * (n - 1 - mean_x)
    forecast_total = max(0.0, last_level * (forecast_days / 7.0))

    if abs(slope) < 0.15:
        direction = "flat"
    elif slope > 0:
        direction = "rising"
    else:
        direction = "falling"

    return {
        "slope": round(slope, 2),
        "forecast_30d": round(forecast_total, 1),
        "direction": direction,
    }


def area_demand(area: str) -> dict[str, Any]:
    """Demand index + 30-day forecast for one area."""
    series = _weekly_series(area)
    total = sum(series)
    peak = max(series) if series else 0
    recent = sum(series[-4:])  # last 4 weeks

    if total < MIN_SIGNAL or peak == 0:
        return {
            "area": area,
            "demand_index": None,
            "direction": "insufficient",
            "total_signals": total,
            "weekly_series": series,
            "forecast_30d": None,
            "note": "Not enough activity in this area yet to estimate demand.",
        }

    # Index: recent 4-week activity vs the area's own peak week (0-100).
    index = min(100, round((recent / 4) / peak * 100))
    trend = _linear_trend(series)

    return {
        "area": area,
        "demand_index": index,
        "direction": trend["direction"],
        "total_signals": total,
        "weekly_series": series,
        "forecast_30d": trend["forecast_30d"],
        "note": (
            "Demand estimate from anonymized booking/wishlist/view counts over "
            f"the last {LOOKBACK_WEEKS} weeks — a simple trend, not a seasonal model."
        ),
    }


def area_demand_summary() -> dict[str, Any]:
    """Demand snapshot for every area with listings — the map/overview view."""
    areas = list(Room.objects.values_list("area", flat=True).distinct())
    rows = [area_demand(a) for a in areas]
    rising = [r["area"] for r in rows if r.get("direction") == "rising"]
    falling = [r["area"] for r in rows if r.get("direction") == "falling"]
    return {
        "areas": rows,
        "rising": rising,
        "falling": falling,
        "as_of": timezone.now().isoformat(),
    }
