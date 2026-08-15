"""Misc project-level views."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse


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
