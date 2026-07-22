"""Local development settings."""

import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# SQLite is the default for local dev so the project runs immediately with
# no extra setup. PostgreSQL 16 is installed on this machine — to use it
# instead, set DB_ENGINE=postgres in backend/.env and fill in DB_NAME/
# DB_USER/DB_PASSWORD/DB_HOST/DB_PORT for your local instance.
if os.getenv("DB_ENGINE") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "rentora"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ============================================================
# CORS (development only)
# ============================================================
# Allow any origin locally so the Vite dev server (and tools like the
# browsable API / mobile testing) work without maintaining an allow-list.
# Never enabled in production — prod.py pins explicit origins instead.
CORS_ALLOW_ALL_ORIGINS = True
