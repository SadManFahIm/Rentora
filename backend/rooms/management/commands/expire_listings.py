from django.core.management.base import BaseCommand

from rooms.services import expire_listing_tiers


class Command(BaseCommand):
    help = "Revert paid listing tiers (Featured/Premium) that have expired back to Free."

    def handle(self, *args, **options):
        result = expire_listing_tiers()
        self.stdout.write(self.style.SUCCESS(f"Expired {result['expired']} listing promotion(s)."))
