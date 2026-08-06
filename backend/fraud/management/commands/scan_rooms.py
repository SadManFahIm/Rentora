"""Re-run the fraud detector over every room in the database.

Used to backfill risk scores for listings created before the fraud app
existed, and to re-validate the whole catalogue periodically. New rooms are
already scanned automatically via ``fraud.signals``.

Scheduling
----------
No Celery setup exists yet (see ``pricing`` and ``payments`` for the same
pattern), so run this from a cron/Task Scheduler entry, e.g.:

    0 4 * * * cd /path/to/backend && venv/bin/python manage.py scan_rooms
"""

from django.core.management.base import BaseCommand

from rooms.models import Room

from fraud.models import FraudReport
from fraud.services.detectors import run_scan


class Command(BaseCommand):
    help = "Re-scan every room with the fraud detector and report the results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print every room line-by-line.",
        )

    def handle(self, *args, **options):
        rooms = Room.objects.all()
        total = rooms.count()
        flagged = 0
        clean = 0

        self.stdout.write(f"Scanning {total} room(s)...")
        for room in rooms:
            report = run_scan(room)
            if report.is_flagged:
                flagged += 1
                self.stdout.write(
                    f"  ⚠ {room.title} [{report.severity}] score={report.score} ({report.summary})"
                )
            else:
                clean += 1
                if options.get("verbose"):
                    self.stdout.write(f"  ✓ {room.title} (clean)")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {total} scanned, {flagged} flagged, {clean} clean."
            )
        )
