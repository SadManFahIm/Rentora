"""Price insight: compare a room's listed price against its market segment.

Deliberately simple and explainable — a percentage difference from the
segment average, bucketed into five plain-English classifications. Nothing
is trained here; this only reads the `MarketStat` snapshot computed by
`pricing.services.market_stats.calculate_market_stats`. Contrast with
`pricing.services.prediction`, which answers a different question ("what
should a *new* listing be priced at") via a regression model — this module
only ever answers "how does this *existing* price compare to the market".
"""

from __future__ import annotations

from typing import Any

from rooms.models import Room

from ..models import MarketStat

# A MarketStat built from fewer than this many rooms is too small a sample
# to support a meaningful comparison — better to show no insight at all than
# a confident-looking classification built from one or two listings.
MIN_SAMPLE_SIZE = 3

# Classification thresholds, as a percentage difference from the market average.
GREAT_DEAL_THRESHOLD = -15
GOOD_PRICE_THRESHOLD = -5
FAIR_PRICE_THRESHOLD = 5
ABOVE_AVERAGE_THRESHOLD = 15

_MESSAGES = {
    "great_deal": "{pct}% below the market average — a great deal.",
    "good_price": "{pct}% below the market average — a good price.",
    "fair_price": "Priced close to the market average ({signed_pct}%).",
    "above_average": "{pct}% above the market average.",
    "overpriced": "{pct}% above the market average — priced high for this area.",
}


def _classify(percentage_diff: float) -> str:
    if percentage_diff < GREAT_DEAL_THRESHOLD:
        return "great_deal"
    if percentage_diff < GOOD_PRICE_THRESHOLD:
        return "good_price"
    if percentage_diff <= FAIR_PRICE_THRESHOLD:
        return "fair_price"
    if percentage_diff <= ABOVE_AVERAGE_THRESHOLD:
        return "above_average"
    return "overpriced"


def _message(classification: str, percentage_diff: float) -> str:
    return _MESSAGES[classification].format(
        pct=abs(round(percentage_diff, 1)),
        signed_pct=round(percentage_diff, 1),
    )


def get_price_insight(room: Room) -> dict[str, Any] | None:
    """Return `room`'s price insight, or None if there isn't yet a market
    segment (or a big-enough one — see MIN_SAMPLE_SIZE) to compare it
    against. Callers (the RoomDetailSerializer field, the standalone
    endpoint) should both render that as a null/absent value rather than a
    misleading "0% difference"."""
    try:
        stat = MarketStat.objects.get(area=room.area, room_type=room.room_type)
    except MarketStat.DoesNotExist:
        return None

    if stat.sample_size < MIN_SAMPLE_SIZE:
        return None

    avg_price = float(stat.avg_price)
    your_price = float(room.price)
    percentage_diff = round(((your_price - avg_price) / avg_price) * 100, 1) if avg_price else 0.0
    classification = _classify(percentage_diff)

    return {
        "avg_price": avg_price,
        "your_price": your_price,
        "percentage_diff": percentage_diff,
        "classification": classification,
        "message": _message(classification, percentage_diff),
        "sample_size": stat.sample_size,
    }
