"""Re-run the fraud detector over every room in the database.

Used to backfill risk scores for listings created before the fraud app
existed, and to re-validate the whole catalogue periodically. Also scheduled
as the daily ``fraud.tasks.scan_all_rooms`` beat task — both paths call the
shared :func:`fraud.services.catalogue.scan_all_rooms`.
"""

from django.core.management.base import BaseCommand

from fraud.services.catalogue import scan_all_rooms


class Command(BaseCommand):
    help = "Re-scan every room with the fraud detector and report the results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print every room line-by-line.",
        )

    def handle(self, *args, **options):
        result = scan_all_rooms()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {result['scanned']} scanned, {result['flagged']} flagged, "
                f"{result['scanned'] - result['flagged']} clean."
            )
        )
