"""Shared upload validation (size / extension / content-type guards).

Room-image uploads go through this; KYC documents already validate inline in
the upload view (users/views.py). Keeping one definition here means the rules
stay consistent across surfaces and are easy to tighten in one place.

Rules:
  * 5 MB size cap per file (matches the KYC document cap).
  * Extension allow-list (.jpg/.jpeg/.png/.webp/.gif).
  * Content-type allow-list when the client sends one — the content type is
    treated as a hint, never the only check (clients can lie about it), which
    is why DRF's ``ImageField`` still runs Pillow verification on top.
"""

from __future__ import annotations

import os

from rest_framework import serializers

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def validate_image_upload(value):
    """DRF validator for an uploaded image file.

    Raises ``serializers.ValidationError`` for disallowed extensions,
    unsupported content types, and files over the size cap.
    """
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError("Only JPG, PNG, WebP or GIF images are accepted.")
    content_type = getattr(value, "content_type", "")
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise serializers.ValidationError("Unsupported image content type.")
    if value.size > MAX_UPLOAD_SIZE:
        raise serializers.ValidationError("Images must be 5 MB or smaller.")
    return value
