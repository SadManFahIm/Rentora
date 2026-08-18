"""AI Property Comparison (Tier 4) — side-by-side listing comparison.

Deterministic and grounded: every column is computed from the rooms' own
database rows plus the shared market snapshot (``MarketStat``) and the
existing listing-quality scorer. Nothing is invented — when an area market
is too thin or a room lacks data, the cell is ``null`` with an honest note.

Supports 2-5 rooms. Output is a normalized table:

- ``rooms`` — per-room fact cards (price, price/sqft, area, type, verified,
  amenities, quality score, market position).
- ``columns`` — the comparison matrix keyed by column id, ready for the
  frontend to render as a table without re-deriving anything.
- ``summary`` — one-line takeaways (cheapest, best value, most verified).

Privacy: public listing fields only — the same set the rooms list exposes.
"""

from __future__ import annotations

from typing import Any

from .listing_quality import get_listing_quality
from .models import Room


def _market_stats_map():
    from pricing.models import MarketStat

    return {(stat.area, stat.room_type): stat for stat in MarketStat.objects.all()}


def compare_rooms(rooms: list[Room]) -> dict[str, Any]:
    """Build the comparison payload for ``rooms`` (2-5 validated rooms)."""
    market = _market_stats_map()
    room_cards: list[dict[str, Any]] = []
    columns: dict[str, dict[str, Any]] = {
        "price": {"label": "Rent (৳/mo)", "values": {}},
        "price_per_sqft": {"label": "৳ per sqft", "values": {}},
        "area": {"label": "Area", "values": {}},
        "room_type": {"label": "Type", "values": {}},
        "verified": {"label": "Verified", "values": {}},
        "size_sqft": {"label": "Size (sqft)", "values": {}},
        "amenities": {"label": "Amenities", "values": {}},
        "market_position": {"label": "vs Area Market", "values": {}},
        "quality": {"label": "Listing Quality", "values": {}},
    }

    for room in rooms:
        price = float(room.price or 0)
        sqft = room.size_sqft or 0
        price_per_sqft = round(price / sqft, 2) if sqft and price else None
        stat = market.get((room.area, room.room_type))
        quality = get_listing_quality(room, market_stats=market)
        q_score = quality.get("score")

        position = None
        if stat and stat.sample_size >= 3:
            median = float(stat.median_price)
            if price < median * 0.95:
                position = "Below median"
            elif price > median * 1.05:
                position = "Above median"
            else:
                position = "At median"

        room_cards.append(
            {
                "id": room.id,
                "title": room.title,
                "image": (
                    room.images.filter(is_primary=True).first().image.url
                    if room.images.filter(is_primary=True).exists()
                    else (room.images.first().image.url if room.images.exists() else None)
                ),
                "price": price,
                "price_per_sqft": price_per_sqft,
                "area": room.area,
                "room_type": room.get_room_type_display(),
                "verified": room.verified,
                "size_sqft": sqft,
                "amenities": list(room.amenities or []),
                "market_position": position,
                "quality_score": q_score,
            }
        )

        rid = room.id
        columns["price"]["values"][rid] = price
        columns["price_per_sqft"]["values"][rid] = price_per_sqft
        columns["area"]["values"][rid] = room.area
        columns["room_type"]["values"][rid] = room.get_room_type_display()
        columns["verified"]["values"][rid] = bool(room.verified)
        columns["size_sqft"]["values"][rid] = sqft or None
        columns["amenities"]["values"][rid] = list(room.amenities or [])
        columns["market_position"]["values"][rid] = position
        columns["quality"]["values"][rid] = q_score

    summary: dict[str, Any] = {"count": len(rooms)}
    priced = [r for r in room_cards if r["price"]]
    if priced:
        cheapest = min(priced, key=lambda r: r["price"])
        summary["cheapest"] = {
            "id": cheapest["id"],
            "title": cheapest["title"],
            "price": cheapest["price"],
        }
        with_psf = [r for r in priced if r["price_per_sqft"]]
        if with_psf:
            best_value = min(with_psf, key=lambda r: r["price_per_sqft"])
            summary["best_value"] = {
                "id": best_value["id"],
                "title": best_value["title"],
                "price_per_sqft": best_value["price_per_sqft"],
            }
    verified = [r for r in room_cards if r["verified"]]
    summary["verified_count"] = len(verified)

    return {"rooms": room_cards, "columns": columns, "summary": summary}
