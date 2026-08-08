"""Recompute MarketStat rows for every (area, room_type) market segment.

Scheduling
----------
No Celery/Celery-beat setup exists in this project yet (see
`payments/management/commands/send_payment_reminders.py` for the identical
situation), so this is a plain management command meant to be triggered
periodically by an external scheduler. Once Celery is introduced, this same
call should move into a `@shared_task` on a daily `CELERY_BEAT_SCHEDULE`
entry, e.g.:

    CELERY_BEAT_SCHEDULE = {
        "update-market-stats": {
            "task": "pricing.tasks.update_market_stats",
            "schedule": crontab(hour=3, minute=0),  # once daily at 3am
        },
    }

Until then, run it via a system cron entry (Linux/prod), e.g.:

    0 3 * * * cd /path/to/backend && venv/bin/python manage.py update_market_stats

...or Windows Task Scheduler running the equivalent `python manage.py
update_market_stats` daily.
"""

from django.core.management.base import BaseCommand

from pricing.services.market_stats import calculate_market_stats


class Command(BaseCommand):
    help = "Recompute MarketStat rows (avg/median/min/max/percentiles) for every (area, room_type) segment."

    def handle(self, *args, **options):
        stats = calculate_market_stats()

        if not stats:
            self.stdout.write(
                self.style.WARNING("No available rooms found — no market segments to compute.")
            )
            return

        for stat in stats:
            self.stdout.write(
                f"  {stat.area} / {stat.get_room_type_display()}: "
                f"avg=BDT {stat.avg_price} median=BDT {stat.median_price} "
                f"range=[BDT {stat.min_price}, BDT {stat.max_price}] n={stat.sample_size}"
            )

        self.stdout.write(
            self.style.SUCCESS(f"Recalculated market stats for {len(stats)} segment(s).")
        )
