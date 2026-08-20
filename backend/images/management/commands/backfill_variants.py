"""Backfill WebP variants for existing room images.

    python manage.py backfill_variants [--dry-run]

Idempotent: rows already present for a source are skipped (source-hash dedupe).
"""

from __future__ import annotations

from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate WebP variants for every room image missing them."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing.")

    def handle(self, *args, **options):
        from images.services import ensure_variants_for_file, has_variants

        RoomImage = apps.get_model("rooms", "RoomImage")
        generated = 0
        skipped = 0
        failed = 0
        for image in RoomImage.objects.iterator():
            try:
                if has_variants("room_image", image.pk):
                    skipped += 1
                    continue
                if options["dry_run"]:
                    generated += 1
                    continue
                result = ensure_variants_for_file("room_image", image.pk, image.image)
                generated += 1 if result else 0
                failed += 0 if result else 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f"variant failed for image {image.pk}: {exc}")
        self.stdout.write(
            self.style.SUCCESS(f"Done. generated={generated} skipped={skipped} failed={failed}")
        )
