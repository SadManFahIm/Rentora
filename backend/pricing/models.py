from django.db import models

from rooms.models import Room


class MarketStat(models.Model):
    """Aggregated pricing stats for one (area, room_type) market segment.

    Recomputed wholesale by `pricing.services.market_stats.calculate_market_stats`
    (run via `python manage.py update_market_stats`) from every currently
    available room — this table is a snapshot, never hand-edited, so every
    field beyond the two grouping keys is a derived value.

    Used as the comparison baseline for `pricing.services.insight.get_price_insight`:
    a room's price is only classified against a segment once it has enough
    samples (see `insight.MIN_SAMPLE_SIZE`) to make the comparison meaningful.
    """

    area = models.CharField(max_length=50, choices=Room.Area.choices)
    room_type = models.CharField(max_length=10, choices=Room.RoomType.choices)

    avg_price = models.DecimalField(max_digits=10, decimal_places=2)
    median_price = models.DecimalField(max_digits=10, decimal_places=2)
    min_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_price = models.DecimalField(max_digits=10, decimal_places=2)
    percentile_25 = models.DecimalField(max_digits=10, decimal_places=2)
    percentile_75 = models.DecimalField(max_digits=10, decimal_places=2)

    sample_size = models.IntegerField()
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("area", "room_type")
        ordering = ["area", "room_type"]

    def __str__(self):
        return f"{self.area} / {self.get_room_type_display()} (n={self.sample_size})"
