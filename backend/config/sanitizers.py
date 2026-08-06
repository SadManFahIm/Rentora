"""Input sanitization helpers for user-generated text.

Room listings, reviews and the like are plain-text fields — no HTML is ever
expected — so we strip *all* markup rather than allow-listing tags. This
neutralises stored-XSS payloads (e.g. ``<script>``) before they are persisted,
while leaving legitimate prose untouched.
"""

from __future__ import annotations

import bleach


def sanitize_text(value: str | None) -> str | None:
    """Return ``value`` with every HTML tag stripped and entities unescaped.

    ``None`` and blank values pass through unchanged so the helper is safe to
    call on optional fields. Surrounding whitespace is trimmed.
    """
    if not value:
        return value
    # tags=[] + strip=True removes all markup; the result is plain text.
    cleaned = bleach.clean(value, tags=[], attributes={}, strip=True)
    return cleaned.strip()
