"""Prebuild the semantic embedding matrix and persist it to disk.

Production-grade warm-up (Tier 3): instead of letting the first search
request download a model and encode the whole corpus, run this after a
deploy (or on a schedule) so every worker shares the persisted matrix.

    python manage.py prebuild_embeddings

Exit codes: 0 on success or graceful skip, 1 only on unexpected failure.
"""

from django.core.management.base import BaseCommand

from rooms.embedding_service import get_index


class Command(BaseCommand):
    help = "Precompute and persist the semantic embedding matrix for room search."

    def handle(self, *args, **options):
        from rooms.embedding_service import _cache_dir, _embedding_mode

        mode = _embedding_mode()
        self.stdout.write(f"Embedding mode: {mode}")

        index = get_index()
        if index is None:
            self.stdout.write(
                self.style.WARNING(
                    "Semantic search is disabled (SEMANTIC_SEARCH_ENABLED=False) — nothing to build."
                )
            )
            return

        provider = index.provider
        if index.matrix is None:
            self.stdout.write(
                self.style.WARNING("No rooms yet — matrix built empty. Seed data and re-run.")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Provider: {provider.name} · rooms: {len(index.room_ids)} · "
                f"dims: {index.matrix.shape[1]}"
            )
        )
        self.stdout.write(self.style.SUCCESS(f"Cache: {_cache_dir() / provider.name}*"))
