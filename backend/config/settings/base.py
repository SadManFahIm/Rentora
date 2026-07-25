"""
Base settings shared by every environment (dev.py / prod.py).

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/
"""

import os
from datetime import timedelta
from pathlib import Path

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

# backend/config/settings/base.py -> parents: settings, config, backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me-in-production")

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
    "users",
    "rooms",
    "bookings",
    "wishlist",
    "notifications",
    "dashboard",
    "chat",
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
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
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
