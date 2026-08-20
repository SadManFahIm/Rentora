"""Seed the default Phase 16 feature flags. Idempotent — safe to re-run.

    python manage.py sync_flags

Adds: phase16.semantic_search, phase16.optimized_images,
phase16.vector_search, phase16.recommendation_engine, phase16.ab_testing.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from feature_flags.models import FeatureFlag, invalidate_cache

DEFAULT_FLAGS = [
    {
        "key": "phase16.semantic_search",
        "label": "Semantic search v2 (hybrid ranking)",
        "description": "Neural/semantic ranking on top of keyword search.",
        "owner": "platform@rentora.com",
        "status": "enabled",
        "rollout_percentage": 100,
        "cleanup_plan": "Keep enabled; fold into core ranking when proven.",
    },
    {
        "key": "phase16.optimized_images",
        "label": "Optimized image pipeline (WebP variants)",
        "description": "Serve resized/WebP variants instead of originals.",
        "owner": "platform@rentora.com",
        "status": "enabled",
        "rollout_percentage": 100,
        "cleanup_plan": "Keep enabled; remove original-only URLs once fully migrated.",
    },
    {
        "key": "phase16.vector_search",
        "label": "pgvector-backed similarity search",
        "description": "Push semantic ranking down to PostgreSQL pgvector.",
        "owner": "ai@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable via rollout after embedding backfill; retire the in-memory index.",
    },
    {
        "key": "phase16.recommendation_engine",
        "label": "Personalised recommendation engine",
        "description": "Recommendations tuned by views/wishlist/experiments.",
        "owner": "ai@rentora.com",
        "status": "enabled",
        "rollout_percentage": 100,
        "cleanup_plan": "Keep enabled.",
    },
    {
        "key": "phase16.ab_testing",
        "label": "A/B testing / experimentation framework",
        "description": "Expose experiments + variant assignment to the product UI.",
        "owner": "product@rentora.com",
        "status": "enabled",
        "rollout_percentage": 100,
        "cleanup_plan": "Keep enabled while experiments are active.",
    },
]


class Command(BaseCommand):
    help = "Create/update the default Phase 16 feature flags."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for spec in DEFAULT_FLAGS:
            _obj, was_created = FeatureFlag.objects.update_or_create(key=spec["key"], defaults=spec)
            if was_created:
                created += 1
            else:
                updated += 1
        invalidate_cache()
        self.stdout.write(
            self.style.SUCCESS(f"Feature flags ready: {created} created, {updated} updated.")
        )
