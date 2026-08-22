"""WebP variant pipeline (Phase 16).

* Verifies the upload is a *real* image with Pillow (magic bytes + decode),
  guarded against decompression bombs via ``Image.MAX_IMAGE_PIXELS``;
* strips EXIF (privacy + smaller payloads; location data on room photos is a
  leak vector);
* writes WebP variants at fixed widths (thumbnail/small/medium/large);
* keys each variant on the SHA-256 of the source bytes so regeneration after
  a source change replaces (never orphans) the rows.

Design rule (audit finding): originals stay untouched for archival; variants
are derived data and can always be rebuilt via ``backfill_variants``.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from config.images import open_verified_image, source_hash, strip_exif

from .models import ImageVariant

logger = logging.getLogger(__name__)

# size_key -> target max width (px). Kept small enough for cards/galleries;
# the 1280px "large" is the detail-gallery ceiling.
VARIANT_SIZES: dict[str, int] = {
    "thumbnail": 320,
    "small": 640,
    "medium": 960,
    "large": 1280,
}

WEBP_QUALITY = 82


def variant_url(entity_type: str, entity_id: int, size_key: str) -> str | None:
    """Absolute URL for one variant (None when not generated yet)."""
    variant = ImageVariant.objects.filter(
        entity_type=entity_type, entity_id=entity_id, size_key=size_key
    ).first()
    if variant is None:
        return None
    try:
        return variant.file.url
    except Exception:
        return None


def variant_urls(entity_type: str, entity_id: int) -> dict[str, str]:
    """{size_key: url} for all generated variants of an entity."""
    urls = {}
    for variant in ImageVariant.objects.filter(entity_type=entity_type, entity_id=entity_id):
        try:
            urls[variant.size_key] = variant.file.url
        except Exception:
            continue
    return urls


def generate_variants(
    entity_type: str,
    entity_id: int,
    source_data: bytes,
    *,
    commit: bool = True,
) -> dict[str, str]:
    """Generate + persist all WebP variants for one entity's source image.

    Returns {size_key: url} for the generated set (empty dict on failure —
    the caller's original image still works, just un-optimized).
    """
    img, _fmt = open_verified_image(source_data)
    if img is None:
        logger.warning(
            "variant generation skipped: undecodable image for %s:%s", entity_type, entity_id
        )
        return {}
    img = strip_exif(img)
    digest = source_hash(source_data)
    created: dict[str, str] = {}
    for size_key, max_width in VARIANT_SIZES.items():
        variant_img = img.copy()
        if variant_img.width > max_width:
            ratio = max_width / variant_img.width
            variant_img = variant_img.resize(
                (max_width, int(variant_img.height * ratio)),
            )
        if variant_img.mode not in ("RGB", "RGBA", "L", "LA"):
            variant_img = variant_img.convert("RGB")
        buffer = BytesIO()
        variant_img.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=4)
        filename = f"v_{entity_type}_{entity_id}_{size_key}_{digest[:12]}.webp"
        if commit:
            ImageVariant.objects.update_or_create(
                entity_type=entity_type,
                entity_id=entity_id,
                size_key=size_key,
                defaults={
                    "width": variant_img.width,
                    "height": variant_img.height,
                    "format": "webp",
                    "source_hash": digest,
                    "file": ContentFile(buffer.getvalue(), name=filename),
                },
            )
        try:
            created[size_key] = variant_url(entity_type, entity_id, size_key) or f"<{size_key}>"
        except Exception:
            created[size_key] = ""
    return created


def ensure_variants_for_file(entity_type: str, entity_id: int, file_field) -> dict[str, str]:
    """Generate variants from an existing FileField/ImageField source path."""
    try:
        if not file_field:
            return {}
        storage = getattr(file_field, "storage", None) or default_storage
        with storage.open(file_field.name, "rb") as handle:
            return generate_variants(entity_type, entity_id, handle.read())
    except Exception as exc:
        logger.warning("variant generation for %s:%s failed: %s", entity_type, entity_id, exc)
        return {}


def delete_variants(entity_type: str, entity_id: int) -> int:
    """Remove all variant rows+files for an entity (source deletion sync)."""
    variants = ImageVariant.objects.filter(entity_type=entity_type, entity_id=entity_id)
    count = 0
    for variant in variants:
        with suppress(Exception):
            variant.file.delete(save=False)
        count += 1
    variants.delete()
    return count


def has_variants(entity_type: str, entity_id: int) -> bool:
    return ImageVariant.objects.filter(entity_type=entity_type, entity_id=entity_id).exists()
