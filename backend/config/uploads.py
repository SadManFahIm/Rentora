"""Shared upload validation (size / extension / content-type / bytes guards).

Room-image uploads go through this; KYC documents have their own inline
checks (users/views.py) but share the same hardenings via
``config.images``. Keeping one definition here means the rules stay
consistent across surfaces and are easy to tighten in one place.

Rules:
  * 5 MB size cap per file (matches the KYC document cap).
  * Extension allow-list (.jpg/.jpeg/.png/.webp/.gif).
  * Content-type allow-list when the client sends one — the content type is
    treated as a hint, never the only check (clients can lie about it).
  * **Magic-bytes + full decode check** (``config.images.open_verified_image``):
    the file must actually *be* an image — Pillow decodes it under a
    decompression-bomb guard, so a text file renamed ``.jpg`` or a 200 MP
    image that would exhaust memory on resize are both rejected here, not on
    the worker.
  * Dimension bounds: images narrower than ``IMAGE_MIN_DIMENSION`` px are
    too small to be useful thumbnails; images above ``IMAGE_MAX_DIMENSION``
    are rejected (huge source = slow pipelines + wasted bandwidth).
"""

from __future__ import annotations

import os

from django.conf import settings
from rest_framework import serializers

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

# Max images a single listing may carry (create/update payloads).
MAX_ROOM_IMAGES = int(getattr(settings, "MAX_ROOM_IMAGES", 10))


def validate_image_upload(value, *, enforce_min_dimension: bool = True):
    """DRF validator for an uploaded image file.

    Raises ``serializers.ValidationError`` for disallowed extensions,
    unsupported content types, files over the size cap, undecodable/oversized
    images, and out-of-range dimensions.

    ``enforce_min_dimension`` exists for query-image endpoints (e.g. vision
    search) where a small crop is a legitimate input — the security checks
    (bomb guard, max dimension, magic bytes, size cap) still always apply.
    """
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError("Only JPG, PNG, WebP or GIF images are accepted.")
    content_type = getattr(value, "content_type", "")
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise serializers.ValidationError("Unsupported image content type.")
    if value.size > MAX_UPLOAD_SIZE:
        raise serializers.ValidationError("Images must be 5 MB or smaller.")
    _verify_image_bytes(value, enforce_min_dimension=enforce_min_dimension)
    return value


def _verify_image_bytes(value, *, enforce_min_dimension: bool = True) -> None:
    """Re-read the upload, decode it under the bomb guard, check dimensions."""
    from .images import open_verified_image

    try:
        value.seek(0)
        data = value.read()
        value.seek(0)
    except Exception as exc:
        raise serializers.ValidationError("Could not read the uploaded image.") from exc
    img, _fmt = open_verified_image(data)
    if img is None:
        raise serializers.ValidationError(
            "The file is not a decodable image (or exceeds the size limit)."
        )
    min_dim = int(getattr(settings, "IMAGE_MIN_DIMENSION", 128))
    max_dim = int(getattr(settings, "IMAGE_MAX_DIMENSION", 8000))
    if enforce_min_dimension and (img.width < min_dim or img.height < min_dim):
        raise serializers.ValidationError(f"Images must be at least {min_dim}px on each side.")
    if img.width > max_dim or img.height > max_dim:
        raise serializers.ValidationError(f"Images must be at most {max_dim}px on each side.")
