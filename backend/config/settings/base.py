"""
Base settings shared by every environment (dev.py / prod.py).

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/
"""

import logging
import os
from datetime import timedelta
from pathlib import Path

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

# backend/config/settings/base.py -> parents: settings, config, backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me-in-production")

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "auth": "10/hour",
        "chat_upload": "30/hour",
        # Payment initiation is deliberately much tighter than the general
        # "user" scope — there's no legitimate reason to start dozens of
        # payment sessions an hour, and it's a prime target for abuse/testing
        # stolen cards against the gateway.
        "payment_initiate": "5/hour",
        # Gateway callbacks have no user session (AllowAny/no auth), so they
        # can't use the "user" scope; keyed per-IP to absorb legitimate
        # gateway retries while still capping flood/replay attempts.
        "webhook_callback": "20/minute",
    },
}

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
    "alert-kyc-sla-breaches": {
        "task": "users.tasks.alert_kyc_sla_breaches",
        "schedule": 86400.0,  # daily — flag review queues stuck >48h / slipping
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
