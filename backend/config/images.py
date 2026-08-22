"""Shared image-bytes utilities (Phase 16).

The single place that touches uploaded image *bytes* with Pillow:

* ``open_verified_image`` — magic-byte + full-decode verification under a
  decompression-bomb guard (``Image.MAX_IMAGE_PIXELS``);
* ``strip_exif`` — privacy/leak guard (room photos carry GPS/IPTC metadata);
* ``source_hash`` — deterministic dedupe key for derived artifacts.

Both the upload validators (config/uploads.py), the KYC pipeline, and the
WebP variant service (images/services.py) go through here so the bomb-guard
and pixel-cap settings are enforced consistently everywhere.
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def source_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pixel_limit() -> int:
    from django.conf import settings

    return int(getattr(settings, "IMAGE_MAX_PIXELS", 100_000_000))


def open_verified_image(data: bytes):
    """Open + fully decode an image with Pillow under the bomb guard.

    Returns a ``(PIL.Image, format_name)`` tuple, or ``(None, None)`` when the
    bytes are not a decodable image or exceed the pixel cap. Never raises.
    """
    try:
        from PIL import Image

        previous = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = _pixel_limit()
        try:
            img = Image.open(BytesIO(data))
            fmt = (img.format or "").upper()
            img.load()  # full decode → catches truncated/garbage files
            return img, fmt
        finally:
            Image.MAX_IMAGE_PIXELS = previous
    except Exception as exc:  # Pillow errors, corrupt bytes, bomb
        logger.warning("image verification failed: %s", exc)
        return None, None


def strip_exif(img):
    """Return an EXIF-free copy of the image (in-place compatible)."""
    try:
        from PIL import Image
    except Exception:
        return img
    try:
        if not (hasattr(img, "getexif") and img.getexif()):
            return img
    except Exception:
        return img
    data = list(img.getdata())
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGB")
    else:
        img = Image.new(img.mode, img.size)
        img.putdata(data)
    return img
