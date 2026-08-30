"""
Base settings shared by every environment (dev.py / prod.py).

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/
"""

import logging
import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

# backend/config/settings/base.py -> parents: settings, config, backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me-in-production")

# Runtime environment identifier: dev / staging / test / production.
# Derived from the environment so CI and local test runs consistently get
# "test" (debug tools, eager Celery, etc.).
ENVIRONMENT = os.getenv("DJANGO_ENV", "development").lower()

# ============================================================
# Sentry — error tracking. No-op when SENTRY_DSN is not set (local dev),
# so the whole block is safe to leave on everywhere.
# ============================================================
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.getenv("SENTRY_ENV", "production"),
        # 100% of events locally/CI is fine; scale down in prod if cost is a concern.
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,  # keep user emails/IDs out of events by default
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )

INSTALLED_APPS = [
    # Daphne must come before django.contrib.staticfiles so its ASGI-aware
    # runserver replaces the default (WSGI) one.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "channels",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "django_filters",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    # Local apps
    "audit",
    "users",
    "rooms",
    "bookings",
    "wishlist",
    "notifications",
    "dashboard",
    "chat",
    "payments",
    "recommendations",
    "pricing",
    "roommates",
    "fraud",
    "savedsearches",
    "copilot",
    "moderation",
    "disputes",
    "analytics",
    # Phase 16 — Hardening & scale
    "embeddings",
    "feature_flags",
    "experiments",
    "images",
    # Phase 15 — Monetization 2.0
    "subscriptions",
    "monetization",
    "brokers",
    "corporate",
    "marketplace",
    "partner_services",
    # Phase 17 — Graph & Deep Trust
    "ml_models",
    # Phase 18 — AI Intelligence Layer
    "ai_intelligence",
    # Phase 19 — Agent SDK foundation
    "agents",
    # Phase 19.1 — Property Intelligence Score (composite 0-100)
    "property_intelligence",
    # Phase 19.2 — AI Rental Agent (tenant-facing, grounded in real tool data)
    "rental_agent",
]

# ============================================================
# Security headers (Tier-1 quick win) — see config/security.py
# ============================================================
# Content-Security-Policy, one directive per dict entry. The default keeps
# the Django admin and drf-spectacular docs working (inline styles/scripts +
# their CDN assets) while blocking third-party frames, objects and base-URI
# tricks. Override per environment by setting the full dict in prod.py.
SECURITY_CONTENT_SECURITY_POLICY = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
    "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
    "img-src": "'self' data: blob: https:",
    "font-src": "'self' data: https://cdn.jsdelivr.net",
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
}
# Sent with every response unless overridden.
SECURITY_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURITY_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "config.http_middleware.RequestCorrelationMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.security.SecurityHeadersMiddleware",
    "config.http_middleware.CacheControlHeadersMiddleware",
    "recommendations.middleware.RoomViewActivityMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ============================================================
# Django Channels — channel layer
# ============================================================
# Dev defaults to the in-memory layer (single-process, no Redis). Production
# overrides this with the Redis layer in prod.py. The env-driven REDIS_URL
# lets a developer opt into Redis locally by setting CHANNELS_BACKEND=redis.
if os.getenv("CHANNELS_BACKEND") == "redis":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [os.getenv("REDIS_URL", "redis://localhost:6379/0")],
                # Namespace channel keys so a shared Redis instance (dev DB 0,
                # cache DB 1, ...) never collides with other apps.
                "prefix": "rentora:ws:",
                "group_expiry": 86400,
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }

# ============================================================
# Cache — also used for chat online-presence tracking (chat/presence.py).
# Same CHANNELS_BACKEND toggle as above: a single dev process shares state
# fine with LocMemCache, but multi-process (prod) needs Redis so presence is
# consistent across workers. prod.py forces Redis unconditionally.
# ============================================================
if os.getenv("CHANNELS_BACKEND") == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            "KEY_PREFIX": "rentora",
            "OPTIONS": {
                # A slow/hung Redis must fail fast rather than pin the GIL.
                # `retry_on_timeout` re-issues a command once on a short blip;
                # pool sizing keeps one busy connection pool from starving.
                # `protocol: 2` keeps compatibility with Redis < 6 (RESP3's
                # HELLO handshake fails against older servers).
                # (These kwargs are forwarded to redis-py's ConnectionPool.)
                "max_connections": 50,
                "socket_timeout": 1.0,
                "socket_connect_timeout": 1.0,
                "retry_on_timeout": True,
                "protocol": 2,
            },
        }
    }
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================
# Django REST Framework
# ============================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticatedOrReadOnly",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    # OpenAPI schema generation (drf-spectacular).
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Unified error envelope (see config/exceptions.py).
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
    # Rate limiting. Anonymous requests are keyed by IP, authenticated by user.
    # The per-IP `auth` scope is applied explicitly on the login/register views.
    # The *trusted* variants resolve the real client IP behind a proxy
    # (config.throttling + config.ip); NUM_PROXIES is set per deployment.
    "DEFAULT_THROTTLE_CLASSES": (
        "config.throttling.TrustedAnonRateThrottle",
        "config.throttling.TrustedUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "auth": "10/hour",
        "chat_upload": "30/hour",
        # Chat translation — bounded per user; with an http gateway this is
        # real quota spend, so it gets its own scope.
        "chat_translate": "120/hour",
        # Analytics capture is fire-and-forget but still bounded — a busy
        # visitor is fine, a scripted flood filling the event store is not.
        "analytics": "300/hour",
        # Reports are moderation actions — a tight dedicated scope stops one
        # user from flooding the admin queue (see chat.views.ReportRateThrottle).
        "report": "10/hour",
        # Public image search — photo uploads are CPU-bound (fingerprinting);
        # a dedicated scope stops a scripted flood burning the worker.
        "vision": "30/minute",
        # Payment initiation is deliberately much tighter than the general
        # "user" scope — there's no legitimate reason to start dozens of
        # payment sessions an hour, and it's a prime target for abuse/testing
        # stolen cards against the gateway.
        "payment_initiate": "5/hour",
        # Copilot turns hit the search engine — generous but bounded.
        "copilot": "60/hour",
        # AI Rental Agent turns run the full agent loop (LLM + tools), so the
        # scope is tighter than copilot — a chatty human is fine, a scripted
        # flood is not.
        "rental_agent": "40/hour",
        # Gateway callbacks have no user session (AllowAny/no auth), so they
        # can't use the "user" scope; keyed per-IP to absorb legitimate
        # gateway retries while still capping flood/replay attempts.
        "webhook_callback": "20/minute",
        # Experiment exposure/conversion are low-cost but fire frequently from
        # the client; a tight scope stops a scripted flood of the event store.
        "experiments": "300/hour",
    },
}

# How many trusted proxies sit between clients and this app. 0 = directly
# reachable (never trust X-Forwarded-For); N = the app trusts the rightmost N
# XFF hops (config/ip.py). Set per deployment — trusting XFF when there is no
# proxy lets clients spoof their rate-limit identity.
NUM_PROXIES = int(os.getenv("NUM_PROXIES", "0"))

# ============================================================
# drf-spectacular (OpenAPI 3)
# ============================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "Rentora API",
    "DESCRIPTION": "AI-Powered Room Rental Platform API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    "COMPONENT_SPLIT_REQUEST": True,
    # Distinct names for the two "room_type" enums (Room listing vs ChatRoom)
    # so their differing choice sets don't collide during schema generation.
    "ENUM_NAME_OVERRIDES": {
        "ListingRoomTypeEnum": [
            ("single", "Single"),
            ("shared", "Shared"),
            ("studio", "Studio"),
        ],
        "ChatRoomTypeEnum": [("direct", "Direct"), ("group", "Group")],
    },
}

# ============================================================
# Simple JWT
# ============================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ============================================================
# dj-rest-auth
# ============================================================
REST_AUTH = {
    "USE_JWT": True,
    "JWT_AUTH_HTTPONLY": False,
    "JWT_AUTH_RETURN_EXPIRATION": True,
    "TOKEN_MODEL": None,  # JWT-only: no DRF authtoken model needed
    "USER_DETAILS_SERIALIZER": "users.serializers.CustomUserDetailsSerializer",
    "REGISTER_SERIALIZER": "users.serializers.CustomRegisterSerializer",
}

# ============================================================
# django-allauth
# ============================================================
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["username*", "email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "none"

# ============================================================
# CORS
# ============================================================
# Base defaults; dev.py opens this up and prod.py pins it to the real domains.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
# Needed if we ever switch JWTs to cookies; harmless for the Bearer-header flow.
CORS_ALLOW_CREDENTIALS = True
# Explicitly allow the Authorization header (Bearer tokens) on cross-origin
# requests. `authorization` is in corsheaders' defaults already, but we pin it
# here so the contract is obvious and cannot regress.
CORS_ALLOW_HEADERS = list(default_headers)
if "authorization" not in CORS_ALLOW_HEADERS:
    CORS_ALLOW_HEADERS.append("authorization")

# ============================================================
# SSLCommerz (payments) — sandbox credentials only; never commit real keys.
# ============================================================
SSLCOMMERZ_STORE_ID = os.getenv("SSLCOMMERZ_STORE_ID", "")
SSLCOMMERZ_STORE_PASSWORD = os.getenv("SSLCOMMERZ_STORE_PASSWORD", "")
SSLCOMMERZ_IS_SANDBOX = os.getenv("SSLCOMMERZ_SANDBOX", "True") == "True"

# ============================================================
# bKash Tokenized Checkout (payments) — sandbox credentials only.
# ============================================================
BKASH_APP_KEY = os.getenv("BKASH_APP_KEY", "")
BKASH_APP_SECRET = os.getenv("BKASH_APP_SECRET", "")
BKASH_USERNAME = os.getenv("BKASH_USERNAME", "")
BKASH_PASSWORD = os.getenv("BKASH_PASSWORD", "")
BKASH_SANDBOX_BASE_URL = os.getenv(
    "BKASH_SANDBOX_BASE_URL", "https://tokenized.sandbox.bka.sh/v1.2.0-beta"
)
BKASH_IS_SANDBOX = os.getenv("BKASH_IS_SANDBOX", "True") == "True"

# Base URL of the frontend app — used to build the redirect target after a
# bKash callback resolves (bKash itself only ever hits backend URLs).
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# ============================================================
# AI Search & Discovery (Phase 11+) — feature flags & ranking weights
# ============================================================
# Neural semantic search. When ON (default), smart search ranks by a hybrid
# of neural/synonym embeddings + the TF-IDF/LSA lexical index. Set False to
# fall back to the pre-neural TF-IDF-only ranking.
SEMANTIC_SEARCH_ENABLED = os.getenv("SEMANTIC_SEARCH_ENABLED", "True") == "True"
# Optional heavy model for real multilingual embeddings. Only used when the
# `sentence-transformers` package is installed; otherwise the zero-dependency
# synonym-hash provider (embedding_service.LiteEmbeddingProvider) runs.
SEMANTIC_EMBEDDING_MODEL = os.getenv(
    "SEMANTIC_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
# Embedding provider mode (Tier 3/4): "auto" (default) uses sentence-
# transformers when installed else the lite provider; "neural" requires the
# real model (falls back with a warning); "lite" forces the zero-dependency
# provider for dev/CI parity; "hosted" (Tier 4) calls a hosted embeddings
# endpoint (Hugging Face Inference API compatible) with graceful lite
# fallback on any failure — production-grade without shipping the model.
SEMANTIC_EMBEDDING_MODE = os.getenv("SEMANTIC_EMBEDDING_MODE", "auto")
# Hosted embeddings endpoint (Tier 4, mode="hosted"). Any HTTPS server
# implementing the HF Inference API `/embed` contract works — HF Inference
# Endpoints, a self-hosted TEI instance, etc. The token is env-only.
SEMANTIC_EMBEDDING_HOSTED_URL = os.getenv("SEMANTIC_EMBEDDING_HOSTED_URL", "") or None
SEMANTIC_EMBEDDING_HOSTED_TOKEN = os.getenv("SEMANTIC_EMBEDDING_HOSTED_TOKEN", "") or None
SEMANTIC_EMBEDDING_HOSTED_MODEL = os.getenv(
    "SEMANTIC_EMBEDDING_HOSTED_MODEL", "hosted-multilingual"
)

# ============================================================
# Automated KYC provider (Tier 4) — pluggable document verification
# ============================================================
# Master switch for auto-approval. OFF by default: existing behaviour is
# untouched (every submission goes to the human review queue). Turn on only
# when the provider + confidence bar are proven on real documents.
KYC_AUTO_APPROVE_ENABLED = os.getenv("KYC_AUTO_APPROVE_ENABLED", "False") == "True"
# Provider implementation: "rules" = bundled deterministic provider
# (users/kyc_provider.RuleBasedProvider); empty = manual review only.
KYC_PROVIDER = os.getenv("KYC_PROVIDER", "")
# Minimum confidence (0..1) for an automated approval to take effect.
KYC_AUTO_APPROVE_MIN_CONFIDENCE = float(os.getenv("KYC_AUTO_APPROVE_MIN_CONFIDENCE", "0.7"))
# How long an auto-approved verification stays valid.
KYC_VALIDITY_DAYS = int(os.getenv("KYC_VALIDITY_DAYS", "365"))

# ============================================================
# KYC OCR auto-extraction (Phase 15, C4) — see users/kyc_ocr.py
# ============================================================
# ON by default: the OCR layer runs on every upload and stores whatever it
# parses in auto_screen_detail. But KYC_OCR_PROVIDER defaults to "none"
# (no extraction happens without a gateway) — wire an OCR gateway to make it
# extract NID number / name / DOB from the scanned document. The extracted
# fields are *structural* (format checks only) and only add a small,
# explainable score boost — an admin always decides.
KYC_OCR_ENABLED = os.getenv("KYC_OCR_ENABLED", "True") == "True"
KYC_OCR_PROVIDER = os.getenv("KYC_OCR_PROVIDER", "none")
KYC_OCR_GATEWAY_URL = os.getenv("KYC_OCR_GATEWAY_URL", "")
KYC_OCR_GATEWAY_API_KEY = os.getenv("KYC_OCR_GATEWAY_API_KEY", "")

# ============================================================
# KYC Liveness detection (Phase 17, Stage 4) — see users/liveness_provider.py
# ============================================================
# Provider: "rules" (bundled mock, always passes) or "http" (HTTP gateway).
# Empty = no liveness check (user can skip liveness if not required).
KYC_LIVENESS_PROVIDER = os.getenv("KYC_LIVENESS_PROVIDER", "")
KYC_LIVENESS_GATEWAY_URL = os.getenv("KYC_LIVENESS_GATEWAY_URL", "")
KYC_LIVENESS_GATEWAY_API_KEY = os.getenv("KYC_LIVENESS_GATEWAY_API_KEY", "")
# How long a liveness challenge stays valid before expiring (seconds).
KYC_LIVENESS_CHALLENGE_TTL = int(os.getenv("KYC_LIVENESS_CHALLENGE_TTL", "900"))
# How long liveness selfies are kept before auto-deletion (days).
KYC_LIVENESS_RETENTION_DAYS = int(os.getenv("KYC_LIVENESS_RETENTION_DAYS", "90"))

# ============================================================
# KYC Face-match (Phase 17, Stage 4) — see users/face_match_provider.py
# ============================================================
# Provider: "rules" (bundled mock, always passes) or "http" (HTTP gateway).
# Empty = no face-match check.
KYC_FACE_MATCH_PROVIDER = os.getenv("KYC_FACE_MATCH_PROVIDER", "")
KYC_FACE_MATCH_GATEWAY_URL = os.getenv("KYC_FACE_MATCH_GATEWAY_URL", "")
KYC_FACE_MATCH_GATEWAY_API_KEY = os.getenv("KYC_FACE_MATCH_GATEWAY_API_KEY", "")

# ============================================================
# OCR confidence thresholds (Phase 17, Stage 4) — see users/kyc_ocr.py
# ============================================================
# Minimum OCR confidence level to earn the score boost.
# "high" = number + name + DOB, "medium" = number + one of them, "low" = number only.
KYC_OCR_MIN_CONFIDENCE = os.getenv("KYC_OCR_MIN_CONFIDENCE", "medium")

# ============================================================
# Photo-Geo Authenticity (Phase 17, Stage 5) — see fraud/services/photo_geo.py
# ============================================================
# Feature flag: phase17.photo_geo controls the detector (synced by sync_flags).
# Distance threshold: photos farther than this from the room's declared lat/lng
# are flagged as potential stock-photo or stolen-image fraud.
PHOTO_GEO_MISMATCH_THRESHOLD_KM = float(os.getenv("PHOTO_GEO_MISMATCH_THRESHOLD_KM", "5.0"))

# Phase 17 — Model Drift Monitoring (Stage 7)
MODEL_DRIFT_THRESHOLDS = {
    "fraud_signal_rate": {
        "min": None,
        "max": float(os.getenv("DRIFT_FRAUD_SIGNAL_MAX", "0.30")),
        "baseline": 0.10,
    },
    "review_trust_avg": {
        "min": float(os.getenv("DRIFT_REVIEW_TRUST_MIN", "50.0")),
        "max": None,
        "baseline": 70.0,
    },
    "photo_geo_mismatch_rate": {
        "min": None,
        "max": float(os.getenv("DRIFT_PHOTO_GEO_MAX", "0.15")),
        "baseline": 0.05,
    },
}

# Where the precomputed embedding matrix is persisted (production-grade
# warm cache — see `manage.py prebuild_embeddings`). Defaults to
# MEDIA_ROOT/embeddings; point this at a persistent volume in production.
SEMANTIC_EMBEDDING_CACHE_DIR = os.getenv("SEMANTIC_EMBEDDING_CACHE_DIR", "") or None
# Hybrid ranking blend: final = semantic * SEMANTIC_SEARCH_WEIGHT
#                        + lexical  * TFIDF_SEARCH_WEIGHT  (weights need not sum to 1).
SEMANTIC_SEARCH_WEIGHT = float(os.getenv("SEMANTIC_SEARCH_WEIGHT", "0.7"))
TFIDF_SEARCH_WEIGHT = float(os.getenv("TFIDF_SEARCH_WEIGHT", "0.3"))
# Typo tolerance (fuzzy area/gazetteer resolution) on smart search.
FUZZY_SEARCH_ENABLED = os.getenv("FUZZY_SEARCH_ENABLED", "True") == "True"
# Bangla/English/Banglish area alias expansion (rooms/area_aliases.py).
AREA_ALIAS_ENABLED = os.getenv("AREA_ALIAS_ENABLED", "True") == "True"
# Personalized search re-ranking for authenticated users. Hard filters and
# base relevance always win; this only re-orders within the relevant pool.
PERSONALIZED_SEARCH_ENABLED = os.getenv("PERSONALIZED_SEARCH_ENABLED", "True") == "True"
PERSONALIZATION_WEIGHT = float(os.getenv("PERSONALIZATION_WEIGHT", "0.15"))
# Price-anomaly badge on list cards (reuses the pricing prediction engine).
PRICE_ANOMALY_ENABLED = os.getenv("PRICE_ANOMALY_ENABLED", "True") == "True"
# Only badge a listing when |actual - predicted| / predicted >= this (0.20 = 20%).
PRICE_ANOMALY_THRESHOLD = float(os.getenv("PRICE_ANOMALY_THRESHOLD", "0.20"))

# ============================================================
# Listing Intelligence (Phase 11+) — voice search, saved-search AI matching,
# listing quality score, fraud-aware ranking
# ============================================================
# Voice search is browser-side (Web Speech API) — this flag mirrors it so the
# backend docs/config stay the source of truth; the frontend gates the mic
# button on feature detection + VITE_VOICE_SEARCH_ENABLED.
VOICE_SEARCH_ENABLED = os.getenv("VOICE_SEARCH_ENABLED", "True") == "True"
VOICE_SEARCH_LANGUAGE = os.getenv("VOICE_SEARCH_LANGUAGE", "bn-BD")

# AI saved-search matcher: relevance-score every new/updated room against the
# user's saved searches and notify only above SAVED_SEARCH_MATCH_THRESHOLD.
SAVED_SEARCH_AI_MATCHING_ENABLED = os.getenv("SAVED_SEARCH_AI_MATCHING_ENABLED", "True") == "True"
# 0..1 relevance floor: 0.75+ = relevant match, 0.85+ = highly relevant, 0.95+ = excellent.
SAVED_SEARCH_MATCH_THRESHOLD = float(os.getenv("SAVED_SEARCH_MATCH_THRESHOLD", "0.75"))
# Component weights of the match score (must roughly sum to 1).
SAVED_SEARCH_MATCH_WEIGHTS = {
    "area": 0.25,
    "price": 0.20,
    "room_type": 0.15,
    "semantic": 0.20,
    "preference": 0.10,
    "quality": 0.10,
}
# Rentora Copilot (Phase 11 — conversational room discovery). Hybrid:
# deterministic intent parsing + the existing search/ranking pipeline first;
# an optional LLM is a future fallback only — the core experience never
# requires an external model and never hallucinates listings (every claim
# comes from retrieved database rows).
COPILOT_ENABLED = os.getenv("COPILOT_ENABLED", "True") == "True"

# ---- Chat Safety Engine (Phase 12.3) ----
# Rule-based fraud/safety detection on chat messages (see chat/safety.py).
# Detection is conservative by design: low/medium risk delivers with a
# caution warning, high risk flags the message for admin review, and
# critical risk *blocks* it (the sender's message is replaced with a safety
# notice and the raw content is never stored).
CHAT_SAFETY_ENABLED = os.getenv("CHAT_SAFETY_ENABLED", "True") == "True"
# Messages at or above this risk level are replaced with a blocked notice.
CHAT_SAFETY_BLOCK_LEVEL = os.getenv("CHAT_SAFETY_BLOCK_LEVEL", "critical")
# Messages at or above this risk level are flagged for admin review.
CHAT_SAFETY_FLAG_LEVEL = os.getenv("CHAT_SAFETY_FLAG_LEVEL", "high")
# Learned chat-safety classifier (Tier 2, see chat/classifier.py): a
# deterministic Naive-Bayes layer on top of the rules. It can only raise a
# message to medium (flag for human review) or boost a rule-based medium to
# high — it never blocks, and a model mistake degrades to a queue item.
CHAT_SAFETY_ML_ENABLED = os.getenv("CHAT_SAFETY_ML_ENABLED", "True") == "True"
# Posterior threshold: suspicious >= this flags an otherwise rule-clean message.
CHAT_SAFETY_ML_FLAG_CONFIDENCE = float(os.getenv("CHAT_SAFETY_ML_FLAG_CONFIDENCE", "0.60"))
# Posterior threshold: suspicious >= this boosts a rule-based medium to high.
CHAT_SAFETY_ML_BOOST_CONFIDENCE = float(os.getenv("CHAT_SAFETY_ML_BOOST_CONFIDENCE", "0.85"))

# ---- AI Intelligence Layer (Phase 18.1) ----
# Master switch for AI execution telemetry. When False, providers skip
# telemetry logging entirely (zero overhead). When True, providers log
# execution data asynchronously (non-blocking).
AI_TELEMETRY_ENABLED = os.getenv("AI_TELEMETRY_ENABLED", "True") == "True"
# How long to keep AI execution logs (days). Older logs are purged.
AI_EXECUTION_LOG_RETENTION_DAYS = int(os.getenv("AI_EXECUTION_LOG_RETENTION_DAYS", "90"))
# How long dashboard aggregates stay cached (seconds). Short TTL — an ops
# dashboard must not serve stale outliers for long. (Phase 18.4)
AI_DASHBOARD_CACHE_TTL_SECONDS = int(os.getenv("AI_DASHBOARD_CACHE_TTL_SECONDS", "300"))

# ============================================================
# Phase 19 — Agent SDK / Agentic AI Foundation (agents app)
# ============================================================
# Master switch for agentic execution.
AGENTS_ENABLED = os.getenv("AGENTS_ENABLED", "True") == "True"
# Active LLM provider name under the "rentora.agent" feature. Empty means NO
# auto-agent runs: a run terminates with `provider_not_configured` rather than
# silently inventing output. Set to "llm" + AGENTS_LLM_* for the real
# provider, or "mock_llm" (tests/dev only).
AI_AGENT_LLM_PROVIDER = os.getenv("AI_AGENT_LLM_PROVIDER", "").strip()
# OpenAI-compatible ChatCompletions endpoint config.
AGENTS_LLM_API_BASE = os.getenv("AGENTS_LLM_API_BASE", "").strip()
AGENTS_LLM_API_KEY = os.getenv("AGENTS_LLM_API_KEY", "").strip()
AGENTS_LLM_MODEL = os.getenv("AGENTS_LLM_MODEL", "").strip()
AGENTS_LLM_TIMEOUT_SECONDS = int(os.getenv("AGENTS_LLM_TIMEOUT_SECONDS", "30"))
# Default guardrail limits (per-run; agents may override).
AGENTS_DEFAULT_MAX_TURNS = int(os.getenv("AGENTS_DEFAULT_MAX_TURNS", "6"))
AGENTS_DEFAULT_MAX_TOOL_CALLS = int(os.getenv("AGENTS_DEFAULT_MAX_TOOL_CALLS", "20"))
AGENTS_DEFAULT_MAX_TOKENS = int(os.getenv("AGENTS_DEFAULT_MAX_TOKENS", "4000"))
AGENTS_DEFAULT_TIMEOUT_SECONDS = int(os.getenv("AGENTS_DEFAULT_TIMEOUT_SECONDS", "180"))
AGENTS_DEFAULT_MAX_COST_USD = float(os.getenv("AGENTS_DEFAULT_MAX_COST_USD", "2.0"))
# Stop the loop after N consecutive failed tool calls.
AGENTS_MAX_CONSECUTIVE_TOOL_FAILURES = int(os.getenv("AGENTS_MAX_CONSECUTIVE_TOOL_FAILURES", "3"))
# Human-review proposal TTL (seconds). Pending proposals expire after this.
AGENTS_PROPOSAL_TTL_SECONDS = int(os.getenv("AGENTS_PROPOSAL_TTL_SECONDS", "86400"))
# How many of the most recent transcript messages are sent to the model.
AGENTS_CONTEXT_WINDOW_MESSAGES = int(os.getenv("AGENTS_CONTEXT_WINDOW_MESSAGES", "40"))
# Register debug tools (debug.echo, debug.marker). Forced OFF in production
# unless explicitly enabled; automatically on under ENVIRONMENT=test or CI.
AGENTS_DEBUG_TOOLS = os.getenv("AGENTS_DEBUG_TOOLS", "False") == "True"

# ============================================================
# Chat live translation EN⇄BN (Phase 15, B1) — see chat/translation.py
# ============================================================
# Deterministic phrase-table core by default (zero external deps, works in
# CI/dev). CHAT_TRANSLATE_PROVIDER=http additionally POSTs the text to a
# machine-translation gateway (CHAT_TRANSLATE_GATEWAY_URL) and falls back to
# the phrase core on any gateway failure. The phrase core also feeds the
# safety engine's cross-lingual scan (chat/safety.detect_crosslingual), which
# never consults the gateway.
CHAT_TRANSLATE_ENABLED = os.getenv("CHAT_TRANSLATE_ENABLED", "True") == "True"
CHAT_TRANSLATE_PROVIDER = os.getenv("CHAT_TRANSLATE_PROVIDER", "phrase")
CHAT_TRANSLATE_GATEWAY_URL = os.getenv("CHAT_TRANSLATE_GATEWAY_URL", "")
CHAT_TRANSLATE_GATEWAY_API_KEY = os.getenv("CHAT_TRANSLATE_GATEWAY_API_KEY", "")

# ============================================================
# ClamAV virus scanning for chat uploads (Tier 2) — see chat/antivirus.py
# ============================================================
# Opt-in: dev/CI run without a clamd daemon (scan reports unavailable and
# the existing type/size checks stay the gate). Production sets True once
# clamav/clamd is running and reachable at CLAMAV_HOST:CLAMAV_PORT.
CLAMAV_ENABLED = os.getenv("CLAMAV_ENABLED", "False") == "True"
CLAMAV_HOST = os.getenv("CLAMAV_HOST", "127.0.0.1")
CLAMAV_PORT = int(os.getenv("CLAMAV_PORT", "3310"))
CLAMAV_TIMEOUT_SECONDS = int(os.getenv("CLAMAV_TIMEOUT_SECONDS", "10"))

# ============================================================
# OSRM commute ETA (Tier 2) — see rooms/osrm.py
# ============================================================
# Off by default (safe rollout): the map keeps its straight-line/MRT
# heuristics until OSRM_ENABLED=True and OSRM_URL points at a routing
# server. The free public demo works for dev; production should self-host
# OSRM (open-source, one Docker command — Phase 8).
OSRM_ENABLED = os.getenv("OSRM_ENABLED", "False") == "True"
OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")
OSRM_TIMEOUT_SECONDS = int(os.getenv("OSRM_TIMEOUT_SECONDS", "3"))
OSRM_CACHE_TTL = int(os.getenv("OSRM_CACHE_TTL", "900"))

# Semantic search result cache (Tier-1 quick win): identical smart-search /
# Copilot queries over the same pool of rooms reuse the last ranking instead
# of recomputing embeddings on every request. Bypassed for authenticated
# (personalized) and debug-metadata requests; ordering may lag a listing
# quality / fraud-score change by at most the TTL.
SEMANTIC_SEARCH_CACHE_ENABLED = os.getenv("SEMANTIC_SEARCH_CACHE_ENABLED", "True") == "True"
# How long a cached ranking stays valid (seconds).
SEMANTIC_SEARCH_CACHE_TTL_SECONDS = int(os.getenv("SEMANTIC_SEARCH_CACHE_TTL_SECONDS", "900"))

# Max listings returned per Copilot turn.
COPILOT_MAX_RESULTS = int(os.getenv("COPILOT_MAX_RESULTS", "5"))
# Follow-up conversation context lives in the Django cache under a random
# session_id; this is its TTL.
COPILOT_SESSION_TTL_SECONDS = int(os.getenv("COPILOT_SESSION_TTL_SECONDS", "3600"))

# A price cut of >= this fraction (0.10 = 10%) since the last check triggers a
# price-drop notification for matching saved searches.
PRICE_DROP_NOTIFICATION_THRESHOLD = float(os.getenv("PRICE_DROP_NOTIFICATION_THRESHOLD", "0.10"))
# Don't re-notify the same user about the same room within this many hours
# (unless something material — e.g. another significant price drop — happens).
SAVED_SEARCH_COOLDOWN_HOURS = int(os.getenv("SAVED_SEARCH_COOLDOWN_HOURS", "24"))

# Listing quality score (rooms/listing_quality.py) — transparent 0-100
# completeness score, exposed on detail + landlord insights.
LISTING_QUALITY_SCORE_ENABLED = os.getenv("LISTING_QUALITY_SCORE_ENABLED", "True") == "True"
# Category weights (sum 100) — adapt to the actual Room model fields.
LISTING_QUALITY_WEIGHTS = {
    "basic": 20,
    "description": 20,
    "photos": 20,
    "location": 15,
    "amenities": 15,
    "pricing": 10,
}
# (min_score, level) thresholds, descending.
LISTING_QUALITY_LEVELS = [
    (90, "excellent"),
    (75, "good"),
    (60, "fair"),
    (40, "needs_improvement"),
    (0, "poor"),
]
# Quality as a *secondary* search-ranking signal — tiny weight, applied only
# within the already-relevant pool so it can never override query/area/price.
LISTING_QUALITY_RANKING_ENABLED = os.getenv("LISTING_QUALITY_RANKING_ENABLED", "True") == "True"
LISTING_QUALITY_RANKING_WEIGHT = float(os.getenv("LISTING_QUALITY_RANKING_WEIGHT", "0.05"))

# ============================================================
# Property Intelligence score (Phase 19.1) — composite 0-100
# ============================================================
# Transparent, deterministic, versioned composite of listing quality, price
# competitiveness, location/commute, photo authenticity, trust and demand.
# Reuses existing engines (listing_quality, price insight, market stats,
# fraud/trust signals, demand counts); see docs/phase-19-property-intelligence.md.
PROPERTY_INTELLIGENCE_ENABLED = os.getenv("PROPERTY_INTELLIGENCE_ENABLED", "True") == "True"
# Component weights — must be all six components, non-negative, sum 100.
# Malformed values log a warning and fall back to these documented defaults.
PROPERTY_INTELLIGENCE_WEIGHTS = {
    "listing_quality": 25,
    "price_value": 20,
    "location": 15,
    "photo_trust": 15,
    "trust": 15,
    "demand": 10,
}
# Redis/LocMem TTL for the computed score (demand self-refreshes on expiry).
PROPERTY_INTELLIGENCE_CACHE_TTL_SECONDS = int(
    os.getenv("PROPERTY_INTELLIGENCE_CACHE_TTL_SECONDS", "900")
)
# A listing untouched for this many days is treated as stale (lower confidence).
PROPERTY_INTELLIGENCE_STALE_DAYS = int(os.getenv("PROPERTY_INTELLIGENCE_STALE_DAYS", "90"))
# Lightweight badge on the room detail serializer (score/confidence/version).
PROPERTY_INTELLIGENCE_SERIALIZER_ENABLED = (
    os.getenv("PROPERTY_INTELLIGENCE_SERIALIZER_ENABLED", "True") == "True"
)

# Fraud-aware search ranking: demote risky listings using the EXISTING fraud
# engine's score (FraudReport.score / 100). Listings are never hidden — only
# penalised in ranking (moderation policy decides visibility, not ranking).
FRAUD_AWARE_RANKING_ENABLED = os.getenv("FRAUD_AWARE_RANKING_ENABLED", "True") == "True"
FRAUD_RANKING_PENALTY_WEIGHT = float(os.getenv("FRAUD_RANKING_PENALTY_WEIGHT", "0.20"))

# Cross-listing duplicate-image fraud detection (fraud/services/detectors.py):
# reuses the pHash cache from rooms/image_search.py to flag the same (or
# visually near-identical) photo re-used across *different* listings — the
# classic scam-listing tell. Images repeated within one listing are fine.
DUPLICATE_IMAGE_FRAUD_ENABLED = os.getenv("DUPLICATE_IMAGE_FRAUD_ENABLED", "True") == "True"
# Max Hamming bits that may differ between two photos before they stop
# counting as the same image (64-bit average hash; 8 tolerates mild
# compression/resize without over-matching).
IMAGE_DUPLICATE_THRESHOLD = int(os.getenv("IMAGE_DUPLICATE_THRESHOLD", "8"))
# A room is only scanned for duplicate images once it has at least this many
# other listings on the platform — with one or two listings there is nothing
# to compare against and hashing every image is pure waste.
IMAGE_DUPLICATE_MIN_LISTINGS = int(os.getenv("IMAGE_DUPLICATE_MIN_LISTINGS", "2"))

# ============================================================
# Content moderation (Phase 12.5 — photo + review moderation)
# ============================================================
# Deterministic review-text and photo moderation with an admin queue.
# Low-risk reviews/photos are auto-approved (published immediately — existing
# behaviour preserved); high-risk ones land in the admin moderation queue.
REVIEW_MODERATION_ENABLED = os.getenv("REVIEW_MODERATION_ENABLED", "True") == "True"
# Reviews scoring at or above this 0-100 risk are held for admin review.
REVIEW_MODERATION_FLAG_THRESHOLD = int(os.getenv("REVIEW_MODERATION_FLAG_THRESHOLD", "60"))
PHOTO_MODERATION_ENABLED = os.getenv("PHOTO_MODERATION_ENABLED", "True") == "True"

# ============================================================
# Alert email throttling (notifications.email_guard)
# ============================================================
# Scheduled alert blasts (KYC SLA breaches, fraud flags, …) are rate-limited
# per recipient per template: at most ALERT_EMAIL_DAILY_BUDGET successful
# sends per day, and after a failure the recipient is not retried until
# ALERT_EMAIL_BACKOFF_HOURS * 2 ** (consecutive_failures - 1) have passed
# (exponential, capped at 7 days). Protects the team from email storms when
# SMTP misbehaves or a queue is genuinely backed up.
ALERT_EMAIL_DAILY_BUDGET = int(os.getenv("ALERT_EMAIL_DAILY_BUDGET", "3"))
ALERT_EMAIL_BACKOFF_HOURS = int(os.getenv("ALERT_EMAIL_BACKOFF_HOURS", "24"))

# ============================================================
# Browser push notifications (notifications.webpush)
# ============================================================
# VAPID key pair — generate once with `python scripts/generate_vapid.py` and
# set in the environment. Unset keys make push a safe no-op (local dev/CI
# never touch a push service). VITE_VAPID_PUBLIC_KEY on the frontend lets the
# browser build the subscription; it is public by design.
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "")

# ============================================================
# Email-OTP two-factor authentication (users app)
# ============================================================
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Rentora <noreply@rentora.com>")
SITE_NAME = os.getenv("SITE_NAME", "Rentora")
# How long a 6-digit sign-in code stays valid.
OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "600"))
# Failed attempts before a challenge locks and a new code is required.
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
# Minimum delay between resend requests for the same challenge.
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30"))

# ============================================================
# Phone (SMS) OTP login (Phase 13 — reach, users app)
# ============================================================
# Master switch — OFF by default; a deployment enables it once an SMS gateway
# is configured (see SMS_PROVIDER below).
SMS_OTP_ENABLED = os.getenv("SMS_OTP_ENABLED", "False") == "True"
# Provider: "console" (default) logs codes to the server log for local
# dev/CI; "http" POSTs a generic gateway (SMS_GATEWAY_URL / API key / sender).
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "console")
SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", "")
SMS_GATEWAY_API_KEY = os.getenv("SMS_GATEWAY_API_KEY", "")
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "")
# Code lifecycle knobs (independent of the email-OTP ones above).
SMS_OTP_TTL_SECONDS = int(os.getenv("SMS_OTP_TTL_SECONDS", "600"))
SMS_OTP_MAX_ATTEMPTS = int(os.getenv("SMS_OTP_MAX_ATTEMPTS", "5"))
SMS_OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("SMS_OTP_RESEND_COOLDOWN_SECONDS", "30"))

# ============================================================
# Vision & content AI (Phase 14 — AI v3, rooms app)
# ============================================================
# Master switch for the deterministic photo pipeline (analysis, drafts,
# image search). Local-only by default — no external calls are made.
VISION_ENABLED = os.getenv("VISION_ENABLED", "True") == "True"
# Provider: "heuristic" (default) derives lighting/tone/décor/framing
# observations from pixels, self-hosted; "http" additionally POSTs the
# listing photos to a configured vision gateway for a caption + object-level
# amenity tags, falling back to heuristic on any gateway failure.
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "heuristic")
VISION_GATEWAY_URL = os.getenv("VISION_GATEWAY_URL", "")
VISION_GATEWAY_API_KEY = os.getenv("VISION_GATEWAY_API_KEY", "")
VISION_GATEWAY_MODEL = os.getenv("VISION_GATEWAY_MODEL", "")
# Image search: how many visual matches to return.
VISION_SEARCH_TOP_K = int(os.getenv("VISION_SEARCH_TOP_K", "8"))

# ============================================================
# WebAuthn / Passkeys (users app)
# ============================================================
# rp_id must match the browser's effective registrable domain — "localhost"
# for local dev (a secure context per spec); prod must share a domain across
# the SPA and API (e.g. app.example.com + api.example.com → rp_id "example.com").
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "Rentora")
WEBAUTHN_ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:3000")

# ============================================================
# Payments — business rules & webhook hardening (Phase 5 Day 3)
# ============================================================
# Whether a landlord may approve a booking that has an unpaid security
# deposit attached. Off by default so platforms/rooms that don't require a
# deposit are never blocked; flip on via env once deposit collection is a
# hard requirement.
REQUIRE_SECURITY_DEPOSIT_BEFORE_APPROVAL = (
    os.getenv("REQUIRE_SECURITY_DEPOSIT_BEFORE_APPROVAL", "False") == "True"
)

# ============================================================
# Paid listing tiers (monetization) — Phase 9
# ============================================================
# Price (BDT) per tier for a single promotion period. `free` is a valid
# value but never purchasable — it's the default tier every new listing
# starts with. The amount is derived server-side from this table (never
# client-supplied), exactly like booking rents.
LISTING_TIER_PRICING = {
    "free": 0,
    "featured": 199,
    "premium": 499,
}

# How long a purchased Featured/Premium promotion lasts (days).
LISTING_TIER_DURATION_DAYS = 30


# ============================================================
# Phase 16 — Embeddings & vector search (pgvector)
# ============================================================
# Master switch for the DB-backed vector path. When OFF (default), search uses
# the existing in-memory/disk semantic index exactly as before. When ON and
# embeddings exist for the candidate pool, ranking is pushed down to pgvector.
VECTOR_SEARCH_ENABLED = os.getenv("VECTOR_SEARCH_ENABLED", "False") == "True"
# Embedding provider for the pipeline: "lite" (zero-dependency synonym-hash,
# default), "auto"/"neural" (sentence-transformers when installed), "hosted"
# (external endpoint). Reuses the rooms.embedding_service provider contract.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "lite")
# Fixed vector dimension stored in the pgvector column (see migration 0001).
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "384"))
# Max neighbours returned by a vector search.
VECTOR_SEARCH_TOP_K = int(os.getenv("VECTOR_SEARCH_TOP_K", "8"))

# ============================================================
# Phase 16 — Image pipeline (WebP variants, upload hardening)
# ============================================================
# Decompression-bomb ceiling for decoded uploads/variants (Pillow MAX_IMAGE_PIXELS).
IMAGE_MAX_PIXELS = int(os.getenv("IMAGE_MAX_PIXELS", "100000000"))
# Reject uploads outside these dimension bounds (see config/uploads.py).
IMAGE_MIN_DIMENSION = int(os.getenv("IMAGE_MIN_DIMENSION", "128"))
IMAGE_MAX_DIMENSION = int(os.getenv("IMAGE_MAX_DIMENSION", "8000"))
# Max images a single listing may carry.
MAX_ROOM_IMAGES = int(os.getenv("MAX_ROOM_IMAGES", "10"))
# Root for private (non-publicly-served) uploads — KYC/tenant documents.
MEDIA_PRIVATE_ROOT = os.getenv("MEDIA_PRIVATE_ROOT", "") or BASE_DIR / "private_media"
# Phase 16 — request body size limits (protect against abuse / OOM).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB — DRF parser limit
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

# Application version string exposed in health check and error reports.
APP_VERSION = os.getenv("APP_VERSION", "dev")

# ============================================================
# Phase 16 — Redis & presence hardening
# ============================================================
# Chat presence leases (chat/presence.py): a connection counts as online while
# its lease is younger than this; leases self-expire, so a hard-killed worker
# can never leave a user permanently "online". Consumers heartbeat every 60s.
PRESENCE_CONNECTION_TTL = int(os.getenv("PRESENCE_CONNECTION_TTL", "180"))

# ============================================================
# Phase 15 — Monetization 2.0 (Revenue)
# ============================================================
# Master switches for each revenue domain (env convention, default on).
SUBSCRIPTIONS_ENABLED = os.getenv("SUBSCRIPTIONS_ENABLED", "True") == "True"
BROKER_NETWORK_ENABLED = os.getenv("BROKER_NETWORK_ENABLED", "True") == "True"
CORPORATE_ENABLED = os.getenv("CORPORATE_ENABLED", "True") == "True"
MARKETPLACE_ENABLED = os.getenv("MARKETPLACE_ENABLED", "True") == "True"
INSURANCE_ENABLED = os.getenv("INSURANCE_ENABLED", "True") == "True"
CREDIT_ENABLED = os.getenv("CREDIT_ENABLED", "True") == "True"
MONETIZATION_LEDGER_ENABLED = os.getenv("MONETIZATION_LEDGER_ENABLED", "True") == "True"

# Feature keys every signed-up user gets for free (the free tier baseline).
SUBSCRIPTION_FREE_FEATURES = ["price_prediction_basic"]

# Length (days) of one subscription billing period.
SUBSCRIPTION_PERIOD_DAYS = {"monthly": 30, "yearly": 365}

# Default commission rates (%) per revenue scope, used when no CommissionRule
# exists for the scope. Values are server-side percentages.
COMMISSION_DEFAULT_RATES = {
    "broker": 2.0,
    "corporate": 1.0,
    "marketplace": 10.0,
    "insurance": 8.0,
    "credit": 3.0,
}

# Insurance/credit provider selection (mirrors KYC/VISION provider pattern).
INSURANCE_PROVIDER = os.getenv("INSURANCE_PROVIDER", "rule")
INSURANCE_GATEWAY_URL = os.getenv("INSURANCE_GATEWAY_URL", "")
CREDIT_PROVIDER = os.getenv("CREDIT_PROVIDER", "rule")


# Number of monthly installments to generate for an approved booking whose
# `check_out` is open-ended (no fixed lease end date).
DEFAULT_LEASE_SCHEDULE_MONTHS = int(os.getenv("DEFAULT_LEASE_SCHEDULE_MONTHS", "12"))

# ============================================================
# Celery — async task queue (Phase 9)
# ============================================================
# Empty broker (the default) => eager mode: tasks run synchronously in the
# calling process, so local dev + tests need no Redis. Production sets
# CELERY_BROKER_URL=redis://... which disables eager mode automatically.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "")
CELERY_TASK_ALWAYS_EAGER = not CELERY_BROKER_URL
CELERY_TASK_EAGER_PROPAGATES = True  # surface task errors in tests instead of hiding them
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = "Asia/Dhaka"

# Phase 16 — Celery reliability hardening.
# Retry on broker connection loss; ack late so a crashed worker requeues.
# Soft/hard time limits prevent stuck tasks from holding workers forever.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 min — raises SoftTimeLimitExceeded
CELERY_TASK_TIME_LIMIT = 600  # 10 min — hard kill
CELERY_TASK_DEFAULT_RETRY_DELAY = 60
CELERY_TASK_MAX_RETRIES = 3

# Auto-index rooms into the embedding store on save/delete. On by default only
# with a real broker (production): enqueueing is cheap, but eager-mode dev/CI
# would run the (idempotent) pipeline synchronously on every room write, so
# there embeddings are built explicitly via `backfill_embeddings`. Can be
# force-enabled with EMBEDDING_INDEX_ON_SAVE=1.
EMBEDDING_INDEX_ON_SAVE = (
    os.getenv("EMBEDDING_INDEX_ON_SAVE", "") == "1" or not CELERY_TASK_ALWAYS_EAGER
)

# ============================================================
# Rental market report (Phase 15, C6) — see analytics/market_report.py
# ============================================================
# Master switch for the weekly market-report task (snapshot + subscriber
# emails). The public GET endpoint stays read-only regardless.
MARKET_REPORT_ENABLED = os.getenv("MARKET_REPORT_ENABLED", "True") == "True"

# Analytics retention (Phase 16, Stage 8) — events older than this many days
# are purged daily by analytics.tasks.purge_expired_events (keeps the
# first-party event store bounded and GDPR-friendly).
ANALYTICS_EVENT_RETENTION_DAYS = int(os.getenv("ANALYTICS_EVENT_RETENTION_DAYS", "365"))

# Scheduled maintenance (only effective with a real broker + `celery beat`):
CELERY_BEAT_SCHEDULE = {
    "expire-listing-tiers": {
        "task": "rooms.tasks.expire_listing_tiers",
        "schedule": 3600.0,  # hourly — promotions roll off promptly
    },
    "update-market-stats": {
        "task": "pricing.tasks.update_market_stats",
        "schedule": 86400.0,  # daily
    },
    "scan-rooms-fraud": {
        "task": "fraud.tasks.scan_all_rooms",
        "schedule": 86400.0,  # daily catalogue re-validation
    },
    "send-payment-reminders": {
        "task": "payments.tasks.send_payment_reminders",
        "schedule": 86400.0,  # daily
    },
    "check-saved-searches": {
        "task": "savedsearches.tasks.check_saved_searches",
        "schedule": 86400.0,  # daily
    },
    "send-saved-search-digests": {
        "task": "savedsearches.tasks.send_saved_search_digests",
        "schedule": 86400.0,  # daily — one branded email per user with matches
    },
    "alert-kyc-sla-breaches": {
        "task": "users.tasks.alert_kyc_sla_breaches",
        "schedule": 86400.0,  # daily — flag review queues stuck >48h / slipping
    },
    # Phase 15, C6 — weekly rental market report (Monday 06:00 Asia/Dhaka).
    "generate-market-report": {
        "task": "analytics.tasks.generate_market_report",
        "schedule": crontab(minute=0, hour=6, day_of_week=1),
    },
    # Phase 16, Stage 8 — daily purge of analytics events past retention.
    "purge-expired-analytics": {
        "task": "analytics.tasks.purge_expired_events",
        "schedule": 86400.0,
    },
    # Phase 15, D8 — weekly fraud-ring recompute + re-scan (Monday 02:00).
    "detect-fraud-rings": {
        "task": "fraud.tasks.detect_rings",
        "schedule": crontab(minute=0, hour=2, day_of_week=1),
    },
    # Phase 15 — Monetization 2.0: expire finished subscriptions + send
    # renewal reminders daily.
    "process-subscription-renewals": {
        "task": "subscriptions.tasks.process_subscription_renewals",
        "schedule": 86400.0,
    },
    "send-subscription-reminders": {
        "task": "subscriptions.tasks.send_subscription_reminders",
        "schedule": 86400.0,
    },
    # Phase 17 — Graph & Deep Trust (Stage 2 stubs — active in Stages 3-7)
    "rebuild-fraud-graph": {
        "task": "fraud.tasks.rebuild_fraud_graph",
        "schedule": crontab(minute=0, hour=3, day_of_week=0),  # Sun 03:00
    },
    "update-graph-incremental": {
        "task": "fraud.tasks.update_graph_incremental",
        "schedule": 21600.0,  # every 6 hours
    },
    "scan-review-trust": {
        "task": "fraud.tasks.scan_review_trust",
        "schedule": crontab(minute=0, hour=5),  # daily 05:00
    },
    "detect-review-anomalies": {
        "task": "fraud.tasks.detect_review_anomalies",
        "schedule": crontab(minute=30, hour=5),  # daily 05:30
    },
    "check-model-drift": {
        "task": "fraud.tasks.check_model_drift",
        "schedule": crontab(minute=0, hour=6),  # daily 06:00
    },
    "purge-expired-liveness": {
        "task": "fraud.tasks.purge_expired_liveness",
        "schedule": crontab(minute=0, hour=3, day_of_week=1),  # Mon 03:00
    },
    "alert-graph-anomalies": {
        "task": "fraud.tasks.alert_graph_anomalies",
        "schedule": 21600.0,  # every 6 hours
    },
    # Phase 17 — Photo-Geo Authenticity (Stage 5)
    "scan-photo-geo-mismatches": {
        "task": "fraud.tasks.scan_photo_geo_mismatches",
        "schedule": crontab(minute=0, hour=4, day_of_week=1),  # Mon 04:00
    },
    # Phase 18 — AI Intelligence Layer (Stage 1)
    "update-ai-provider-health": {
        "task": "ai_intelligence.update_provider_health",
        "schedule": 3600.0,  # hourly
    },
    "purge-old-ai-execution-logs": {
        "task": "ai_intelligence.purge_old_execution_logs",
        "schedule": crontab(minute=0, hour=2),  # daily 02:00
    },
    # Phase 18.3 — Evaluation Framework
    "cancel-stale-evaluation-runs": {
        "task": "ai_intelligence.cancel_stale_evaluation_runs",
        "schedule": 1800.0,  # every 30 minutes
    },
    # Phase 18.4 — AI Intelligence Dashboard + Alerts
    # Alert rules evaluate every 5 minutes; the dashboard cache warms just
    # after so the admin dashboard's first render is fast.
    "evaluate-ai-alert-rules": {
        "task": "ai_intelligence.evaluate_alert_rules",
        "schedule": 300.0,  # every 5 minutes
    },
    "warm-ai-dashboard-cache": {
        "task": "ai_intelligence.warm_dashboard_cache",
        "schedule": 1800.0,  # every 30 minutes
    },
    # Phase 19 — Agent SDK: expire human-review proposals past their TTL.
    "expire-agent-proposals": {
        "task": "agents.expire_proposals",
        "schedule": 86400.0,  # daily
    },
}

# ============================================================
# Structured logging (Phase 9)
# ============================================================
# JSON logs on stdout in production (see config/logging.JSONFormatter); the
# default console formatter is kept in dev so logs stay human-readable.
if os.getenv("JSON_LOGS", "False") == "True":
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "config.logging.JSONFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
            },
        },
        "root": {"handlers": ["console"], "level": "INFO"},
        "loggers": {
            "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
            "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
        },
    }

# Known gateway webhook source IPs, comma-separated. Sandbox IPs vary and
# aren't published, so this is empty (no enforcement) by default — see
# `payments/services/webhook_security.py`. Populate in production once the
# live gateway's outbound IP ranges are known.
SSLCOMMERZ_WEBHOOK_IP_ALLOWLIST = [
    ip.strip() for ip in os.getenv("SSLCOMMERZ_WEBHOOK_IP_ALLOWLIST", "").split(",") if ip.strip()
]
BKASH_WEBHOOK_IP_ALLOWLIST = [
    ip.strip() for ip in os.getenv("BKASH_WEBHOOK_IP_ALLOWLIST", "").split(",") if ip.strip()
]
