from django.core.management.base import BaseCommand
from django.utils import timezone

from rooms.models import Room


class Command(BaseCommand):
    help = "Revert paid listing tiers (Featured/Premium) that have expired back to Free."

    def handle(self, *args, **options):
        now = timezone.now()
        expired = Room.objects.filter(tier__in=[Room.Tier.FEATURED, Room.Tier.PREMIUM]).filter(
            tier_expires_at__lte=now
        )
        count = expired.update(
            tier=Room.Tier.FREE,
            tier_expires_at=None,
            is_featured=False,
            updated_at=now,
        )
        self.stdout.write(self.style.SUCCESS(f"Expired {count} listing promotion(s)."))
