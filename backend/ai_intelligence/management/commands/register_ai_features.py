"""Seed all real AI features into AIFeatureRegistry.

Idempotent — safe to re-run.

    python manage.py register_ai_features
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ai_intelligence.services import register_feature

# All features that actually exist in the codebase.
# Each entry maps to a real implementation with a real provider.
AI_FEATURES = [
    # Copilot
    {
        "feature_id": "ai.copilot",
        "name": "Rentora Copilot",
        "category": "copilot",
        "description": "FAQ matcher + RAG-powered chat assistant.",
        "owner": "ai@rentora.com",
        "default_provider": "rules",
        "default_model": "",
        "available_providers": ["rules"],
        "settings_key": "COPILOT_ENABLED",
    },
    {
        "feature_id": "ai.copilot.listing",
        "name": "Copilot Listing Q&A",
        "category": "copilot",
        "description": "Grounded Q&A for individual listing details.",
        "owner": "ai@rentora.com",
        "default_provider": "deterministic",
        "available_providers": ["deterministic"],
    },
    {
        "feature_id": "ai.copilot.advisor",
        "name": "AI Rental Advisor",
        "category": "copilot",
        "description": "Budget + income based rental advice from live data.",
        "owner": "ai@rentora.com",
        "default_provider": "deterministic",
        "available_providers": ["deterministic"],
    },
    {
        "feature_id": "ai.copilot.negotiate",
        "name": "AI Negotiation Assistant",
        "category": "copilot",
        "description": "Counter-offer bracket from comparable listings.",
        "owner": "ai@rentora.com",
        "default_provider": "deterministic",
        "available_providers": ["deterministic"],
    },
    # Chat & Communication
    {
        "feature_id": "ai.chat.safety",
        "name": "Chat Safety Engine",
        "category": "chat",
        "description": "Regex + naive-Bayes content safety screening.",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules", "ml"],
        "settings_key": "CHAT_SAFETY_ML_ENABLED",
    },
    {
        "feature_id": "ai.chat.translation",
        "name": "Chat Translation",
        "category": "chat",
        "description": "Auto-detect + translate EN<->BN with phrase table.",
        "owner": "ai@rentora.com",
        "default_provider": "phrase",
        "available_providers": ["phrase", "http"],
        "settings_key": "CHAT_TRANSLATE_PROVIDER",
    },
    {
        "feature_id": "ai.chat.classification",
        "name": "Chat Message Classification",
        "category": "chat",
        "description": "Naive-Bayes message type classifier.",
        "owner": "ai@rentora.com",
        "default_provider": "ml",
        "available_providers": ["ml"],
    },
    # Recommendations
    {
        "feature_id": "ai.recommendation",
        "name": "Room Recommendations",
        "category": "recommendations",
        "description": "Content-based + collaborative filtering recommendations.",
        "owner": "ai@rentora.com",
        "default_provider": "tfidf",
        "available_providers": ["tfidf", "collaborative"],
        "settings_key": "phase16.recommendation_engine",
    },
    {
        "feature_id": "ai.recommendation.similar",
        "name": "Similar Rooms",
        "category": "recommendations",
        "description": "Content-based similar-rooms carousel.",
        "owner": "ai@rentora.com",
        "default_provider": "tfidf",
        "available_providers": ["tfidf"],
    },
    # Pricing
    {
        "feature_id": "ai.pricing.prediction",
        "name": "AI Price Suggestion",
        "category": "pricing",
        "description": "Ridge regression price prediction with demand factor.",
        "owner": "ai@rentora.com",
        "default_provider": "ridge",
        "available_providers": ["ridge"],
    },
    {
        "feature_id": "ai.pricing.demand",
        "name": "Demand Forecasting",
        "category": "pricing",
        "description": "Usage-count based demand index.",
        "owner": "ai@rentora.com",
        "default_provider": "time_series",
        "available_providers": ["time_series"],
    },
    # Search & Discovery
    {
        "feature_id": "ai.search.semantic",
        "name": "Semantic Search",
        "category": "search",
        "description": "Neural/TF-IDF hybrid ranking with cosine similarity.",
        "owner": "ai@rentora.com",
        "default_provider": "tfidf",
        "available_providers": ["tfidf", "neural", "hosted"],
        "settings_key": "SEMANTIC_EMBEDDING_MODE",
    },
    {
        "feature_id": "ai.search.nlp",
        "name": "Natural Language Query Parser",
        "category": "search",
        "description": "Regex-based Bangla/Banglish intent extraction.",
        "owner": "ai@rentora.com",
        "default_provider": "regex",
        "available_providers": ["regex"],
    },
    {
        "feature_id": "ai.search.smart",
        "name": "AI Smart Search",
        "category": "search",
        "description": "NL parser + semantic ranking + intent chips.",
        "owner": "ai@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
    },
    # Fraud Detection
    {
        "feature_id": "ai.fraud.detection",
        "name": "Fraud Auto-Scanner",
        "category": "fraud",
        "description": "6-detector fraud engine (scam, fake, phishing, etc).",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
    },
    {
        "feature_id": "ai.fraud.scam_graph",
        "name": "Scam Network Graph",
        "category": "fraud",
        "description": "PostgreSQL graph with community detection.",
        "owner": "trust@rentora.com",
        "default_provider": "graph",
        "available_providers": ["graph"],
        "settings_key": "phase17.scam_graph",
    },
    {
        "feature_id": "ai.fraud.review_trust",
        "name": "Review Trust Scoring",
        "category": "fraud",
        "description": "Multi-signal trust scoring for reviews.",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
        "settings_key": "phase17.review_trust",
    },
    {
        "feature_id": "ai.fraud.photo_geo",
        "name": "Photo-Geo Authenticity",
        "category": "fraud",
        "description": "GPS cross-reference for uploaded photos.",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
        "settings_key": "phase17.photo_geo",
    },
    {
        "feature_id": "ai.fraud.image_forensics",
        "name": "Image Forensics",
        "category": "fraud",
        "description": "EXIF analysis + ELA photo manipulation detection.",
        "owner": "trust@rentora.com",
        "default_provider": "heuristic",
        "available_providers": ["heuristic", "http"],
    },
    {
        "feature_id": "ai.fraud.duplicate_image",
        "name": "Duplicate Image Detection",
        "category": "fraud",
        "description": "Perceptual hash duplicate detection across listings.",
        "owner": "trust@rentora.com",
        "default_provider": "phash",
        "available_providers": ["phash"],
    },
    # KYC / Identity
    {
        "feature_id": "ai.kyc.ocr",
        "name": "KYC Document OCR",
        "category": "kyc",
        "description": "NID/passport text extraction with confidence scoring.",
        "owner": "trust@rentora.com",
        "default_provider": "http",
        "available_providers": ["http", "rules"],
        "settings_key": "KYC_OCR_PROVIDER",
    },
    {
        "feature_id": "ai.kyc.liveness",
        "name": "KYC Liveness Check",
        "category": "kyc",
        "description": "Selfie anti-spoofing via pluggable provider.",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules", "http"],
        "settings_key": "phase17.kyc_liveness",
    },
    {
        "feature_id": "ai.kyc.face_match",
        "name": "KYC Face Match",
        "category": "kyc",
        "description": "NID-to-selfie comparison via pluggable provider.",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules", "http"],
        "settings_key": "phase17.kyc_face_match",
    },
    # Vision & Image
    {
        "feature_id": "ai.vision.analysis",
        "name": "Photo Intelligence",
        "category": "other",
        "description": "Pillow-based photo analysis (caption, palette, observations).",
        "owner": "ai@rentora.com",
        "default_provider": "heuristic",
        "available_providers": ["heuristic", "http"],
        "settings_key": "VISION_PROVIDER",
    },
    {
        "feature_id": "ai.vision.image_search",
        "name": "AI Image Search",
        "category": "other",
        "description": "Upload a photo, find visually similar listings.",
        "owner": "ai@rentora.com",
        "default_provider": "phash",
        "available_providers": ["phash"],
    },
    # Listing Quality
    {
        "feature_id": "ai.listing.quality",
        "name": "Listing Quality Score",
        "category": "other",
        "description": "Rule-based listing completeness + quality scoring.",
        "owner": "ai@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
    },
    {
        "feature_id": "ai.listing.description",
        "name": "AI Listing Draft",
        "category": "other",
        "description": "Auto-generate title + description from listing fields.",
        "owner": "ai@rentora.com",
        "default_provider": "template",
        "available_providers": ["template"],
    },
    # Moderation
    {
        "feature_id": "ai.review.moderation",
        "name": "Review Moderation",
        "category": "other",
        "description": "Spam detection + quality scoring for reviews.",
        "owner": "trust@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
        "settings_key": "phase17.review_moderation",
    },
    {
        "feature_id": "ai.moderation.photo",
        "name": "Photo Moderation",
        "category": "other",
        "description": "Duplicate + blank image detection in uploads.",
        "owner": "trust@rentora.com",
        "default_provider": "phash",
        "available_providers": ["phash"],
    },
    # Notifications
    {
        "feature_id": "ai.notification.smart",
        "name": "Smart Notification Ranking",
        "category": "other",
        "description": "Priority scoring for notification routing.",
        "owner": "ai@rentora.com",
        "default_provider": "rules",
        "available_providers": ["rules"],
    },
    # Embeddings
    {
        "feature_id": "ai.embeddings",
        "name": "Vector Embeddings",
        "category": "embeddings",
        "description": "Sentence-transformer/vector embeddings for rooms.",
        "owner": "ai@rentora.com",
        "default_provider": "lite",
        "available_providers": ["lite", "neural", "hosted"],
        "settings_key": "EMBEDDING_PROVIDER",
    },
]


class Command(BaseCommand):
    help = "Seed all known AI features into AIFeatureRegistry (idempotent)."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for spec in AI_FEATURES:
            feature = register_feature(**spec)
            # register_feature does update_or_create; we count via created flag
            # by checking if updated_at == created_at (approximate)
            if feature.created_at == feature.updated_at:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"AI features ready: {created} created, {updated} updated "
                f"(total {len(AI_FEATURES)})."
            )
        )
