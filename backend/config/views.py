"""Misc project-level views."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse


def security_txt(request):
    """Serve ``backend/security.txt`` at ``/.well-known/security.txt`` and
    ``/security.txt`` (RFC 9116). Reads the file fresh per request so
    updates don't need a restart; contains no secrets."""
    path = settings.BASE_DIR / "security.txt"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - file ships with the repo
        content = "Contact: mailto:security@rentora.example.com\n"
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


# ============================================================
# Health check (Phase 16)
# ============================================================
# Lightweight liveness probe for load balancers / uptime monitors.
# No auth, no throttle — probes must always pass through.
_started_at = time.monotonic()


def health_check(request):
    """200 with {"status": "ok"} when DB is reachable, 503 otherwise."""
    db_ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        db_ok = False

    status = "ok" if db_ok else "degraded"
    return JsonResponse(
        {
            "status": status,
            "db": "ok" if db_ok else "error",
            "uptime_seconds": int(time.monotonic() - _started_at),
            "ts": datetime.now(UTC).isoformat(),
            "version": getattr(settings, "APP_VERSION", "dev"),
        },
        status=200 if db_ok else 503,
    )
