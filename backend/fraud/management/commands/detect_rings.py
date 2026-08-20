"""Recompute fraud rings and re-scan affected rooms.

Same behaviour as the weekly Celery beat task — a manual run for ops/dev.

    python manage.py detect_rings
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Recompute coordinated-account fraud rings and re-scan affected rooms."

    def handle(self, *args, **options):
        from fraud.services.rings import detect_rings
        from fraud.tasks import detect_rings as run

        result = detect_rings()
        task_result = run()
        self.stdout.write(
            self.style.SUCCESS(
                f"Rings: {result['ring_count']} ({result['user_count']} users), "
                f"rooms re-scanned: {task_result['re_scanned']}"
            )
        )
