"""Market pricing statistics aggregation.

Recomputes one `MarketStat` row per (area, room_type) segment from every
currently-available room, so `pricing.services.insight.get_price_insight`
and `pricing.services.prediction.predict_fair_price` always compare against
an up-to-date snapshot rather than a stale one from whenever this last ran.

Scheduling
----------
No Celery/Celery-beat setup exists in this project yet (see
`payments/management/commands/send_payment_reminders.py` for the identical
situation), so this is recomputed by a plain management command
(`python manage.py update_market_stats`), meant to be triggered daily by an
external scheduler until Celery Beat is introduced. Once it is, this same
`calculate_market_stats()` call should move into a `@shared_task` on a daily
`CELERY_BEAT_SCHEDULE` entry, e.g.:

    CELERY_BEAT_SCHEDULE = {
        "update-market-stats": {
            "task": "pricing.tasks.update_market_stats",
            "schedule": crontab(hour=3, minute=0),  # once daily at 3am
        },
    }
"""

from __future__ import annotations

import numpy as np
from django.db.models import Avg, Count, Min, Max

from rooms.models import Room

from ..models import MarketStat


def calculate_market_stats() -> list[MarketStat]:
    """Recompute and upsert a MarketStat row for every (area, room_type)
    segment that currently has at least one available room.

    Aggregate/min/max/count come from the database (`Avg`/`Min`/`Max`/
    `Count`); percentiles (including the median, i.e. the 50th percentile)
    aren't expressible portably in the Django ORM, so those are computed
    with numpy from the segment's raw price list instead.

    A segment that no longer has any available rooms has its stale
    MarketStat row removed, rather than left showing an outdated baseline.
    Returns the list of upserted (still-current) MarketStat instances.
    """
    segments = (
        Room.objects.filter(is_available=True)
        .values("area", "room_type")
        .annotate(
            avg_price=Avg("price"),
            min_price=Min("price"),
            max_price=Max("price"),
            sample_size=Count("id"),
        )
    )

    updated_pks: list[int] = []
    for segment in segments:
        area, room_type = segment["area"], segment["room_type"]

        prices = np.array(
            list(
                Room.objects.filter(is_available=True, area=area, room_type=room_type).values_list(
                    "price", flat=True
                )
            ),
            dtype=float,
        )

        stat, _ = MarketStat.objects.update_or_create(
            area=area,
            room_type=room_type,
            defaults={
                "avg_price": round(float(segment["avg_price"]), 2),
                "median_price": round(float(np.percentile(prices, 50)), 2),
                "min_price": round(float(segment["min_price"]), 2),
                "max_price": round(float(segment["max_price"]), 2),
                "percentile_25": round(float(np.percentile(prices, 25)), 2),
                "percentile_75": round(float(np.percentile(prices, 75)), 2),
                "sample_size": segment["sample_size"],
            },
        )
        updated_pks.append(stat.pk)

    MarketStat.objects.exclude(pk__in=updated_pks).delete()

    return list(MarketStat.objects.filter(pk__in=updated_pks))
