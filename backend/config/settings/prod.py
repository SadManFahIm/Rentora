"""Production settings. All secrets/hosts/DB config come from the environment."""

import os

from .base import *  # noqa: F403

DEBUG = False

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# ============================================================
# Security hardening (HTTPS-only production)
# ============================================================
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Trusted proxies in front of the app (see config/ip.py). Behind a single
# TLS-terminating load balancer this should be 1; set NUM_PROXIES explicitly
# if the chain is deeper. 0 disables XFF parsing entirely.
NUM_PROXIES = int(os.getenv("NUM_PROXIES", "1"))
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

# ============================================================
# CORS (production)
# ============================================================
# Explicit allow-list — no wildcard. Additional origins can be appended via the
# CORS_ALLOWED_ORIGINS env var (comma-separated) handled in base.py, but the
# canonical production domains are pinned here.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://rentora.com",
    "https://www.rentora.com",
]
CORS_ALLOW_CREDENTIALS = True

# ============================================================
# Django Channels — Redis channel layer (multi-process safe)
# ============================================================
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.getenv("REDIS_URL", "redis://localhost:6379/0")],
            "prefix": "rentora:ws:",
            "group_expiry": 86400,
        },
    }
}

# ============================================================
# Cache — Redis, unconditionally (multi-process safe). Also backs chat
# online-presence tracking (chat/presence.py), which must be consistent
# across every worker process, not just the one a given socket connected to.
# KEY_PREFIX namespaces keys so other apps sharing the same Redis instance
# can never collide with ours; OPTIONS make a down/slow Redis fail fast.
# ============================================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "KEY_PREFIX": "rentora",
        "OPTIONS": {
            "max_connections": 50,
            "socket_timeout": 1.0,
            "socket_connect_timeout": 1.0,
            "retry_on_timeout": True,
            "protocol": 2,
        },
    }
}

# ============================================================
# Celery — production broker (warn if unreachable)
# ============================================================
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "") or CELERY_BROKER_URL
if not CELERY_BROKER_URL:
    import logging as _logging

    _logging.getLogger("rentora").warning(
        "CELERY_BROKER_URL not set — background tasks will fail. "
        "Set it to a Redis/RabbitMQ URL for production."
    )
