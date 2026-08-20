"""Backfill room embeddings in background-safe batches (Phase 16).

Run with a real Celery worker to generate embeddings on the ``embeddings``
queue, or with an empty broker (eager mode) to run synchronously::

    python manage.py backfill_embeddings --batch-size 200 --limit 1000

Progress is tracked by page offset so an interrupted run can resume; every row
is idempotent via its content hash.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from embeddings.tasks import backfill_rooms


class Command(BaseCommand):
    help = "Backfill room embeddings into the vector store in batches."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--limit", type=int, default=0, help="0 = no limit (all rooms)")

    def handle(self, *args, **options):
        batch = max(1, options["batch_size"])
        limit = options["limit"] or None
        offset = 0
        processed = 0
        while True:
            remaining = limit - processed if limit else None
            size = batch if remaining is None else min(batch, remaining)
            if size <= 0:
                break
            result = backfill_rooms(offset=offset, limit=size)
            processed += result["processed"]
            self.stdout.write(
                f"batch offset={offset} processed={result['processed']} "
                f"indexed={result['indexed']} skipped={result['skipped']}"
            )
            if result.get("done"):
                break
            offset += size
        self.stdout.write(self.style.SUCCESS(f"Done. {processed} rooms processed."))
