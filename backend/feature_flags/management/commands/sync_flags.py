"""Seed the default feature flags. Idempotent — safe to re-run.

    python manage.py sync_flags

Phase 16: phase16.semantic_search, phase16.optimized_images,
phase16.vector_search, phase16.recommendation_engine, phase16.ab_testing.

Phase 17: phase17.scam_graph, phase17.kyc_liveness, phase17.kyc_face_match,
phase17.photo_geo, phase17.review_moderation, phase17.review_trust,
phase17.model_monitoring.
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
    # Phase 17 — Graph & Deep Trust
    {
        "key": "phase17.scam_graph",
        "label": "Scam-network graph (persistent edges + community detection)",
        "description": "Persistent graph layer for cross-user coordination fraud detection.",
        "owner": "trust@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after graph rebuild is validated; remove flag once core.",
    },
    {
        "key": "phase17.kyc_liveness",
        "label": "KYC liveness check (selfie anti-spoofing)",
        "description": "Liveness detection in the tenant KYC flow.",
        "owner": "trust@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after liveness provider is validated; fold into KYC core.",
    },
    {
        "key": "phase17.kyc_face_match",
        "label": "KYC face-match (NID-to-selfie comparison)",
        "description": "Face-match between NID photo and liveness selfie.",
        "owner": "trust@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after face-match provider is validated; fold into KYC core.",
    },
    {
        "key": "phase17.photo_geo",
        "label": "Photo-geo authenticity (GPS cross-reference)",
        "description": "Extract GPS from uploaded photos and cross-reference with room area.",
        "owner": "trust@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after GPS extraction pipeline is validated; make core.",
    },
    {
        "key": "phase17.review_moderation",
        "label": "Review moderation queue",
        "description": "Route new reviews through a moderation queue before publishing.",
        "owner": "trust@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after moderation queue is validated; keep as default.",
    },
    {
        "key": "phase17.review_trust",
        "label": "Review trust scoring",
        "description": "Compute trust scores for reviews based on text + behavioral signals.",
        "owner": "trust@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after trust scoring is validated; make core.",
    },
    {
        "key": "phase17.model_monitoring",
        "label": "ML model drift monitoring + retrain dashboard",
        "description": "Track model performance over time and trigger retraining.",
        "owner": "ai@rentora.com",
        "status": "disabled",
        "rollout_percentage": 0,
        "cleanup_plan": "Enable after dashboard is validated; keep as admin tool.",
    },
]


class Command(BaseCommand):
    help = "Create/update the default feature flags (Phase 16 + Phase 17)."

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
