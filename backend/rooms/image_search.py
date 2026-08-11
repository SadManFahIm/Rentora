"""Visual room search — find listings whose photos look alike (Phase 11).

Implementation: 64-bit average perceptual hashes (pHash) over each room's
primary photo, computed with Pillow and cached in ``RoomImageHash`` keyed by
the source file's mtime. "Similar" means a small Hamming distance between
hashes — robust to resizing, mild compression and exposure shifts, which is
exactly what matters for spotting look-alike flats (or the same photo
re-used across listings).

Purely best-effort: rooms without images, unreadable files, or a missing
Pillow all degrade to an empty result instead of an error. The endpoint is a
discovery aid (\"rooms that look like this one\"), never a hard filter.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from .models import Room, RoomImage, RoomImageHash

logger = logging.getLogger(__name__)

_HASH_SIZE = 8  # 8x8 -> 64 bits
_DEFAULT_MAX_DISTANCE = 12  # bits that may differ before two photos stop "matching"
_DEFAULT_TOP_K = 8


def average_hash(phash_image, hash_size: int = _HASH_SIZE) -> str | None:
    """64-bit average hash (hex) of a Pillow image, or None on failure."""
    try:
        img = phash_image.convert("L").resize((hash_size, hash_size))
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        return f"{int(bits, 2):016x}"
    except Exception as exc:
        logger.warning("pHash failed: %s", exc)
        return None


def hamming_distance(a: str, b: str) -> int:
    """Number of differing bits between two hex hashes."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _hash_for_image(image: RoomImage) -> str | None:
    """Return (and cache) the pHash for an image, honouring file mtime."""
    from django.utils.timezone import make_aware

    try:
        from pathlib import Path

        path = Path(image.image.path)
        mtime = make_aware(timezone.datetime.fromtimestamp(path.stat().st_mtime))
    except Exception:
        return None

    cached = RoomImageHash.objects.filter(image=image).first()
    if cached and cached.image_updated_at >= mtime.replace(microsecond=0):
        return cached.phash_hex

    try:
        from PIL import Image

        with Image.open(path) as img:
            phash = average_hash(img)
    except Exception as exc:
        logger.warning("Could not hash %s: %s", path, exc)
        return None
    if not phash:
        return None

    RoomImageHash.objects.update_or_create(
        image=image,
        defaults={"room": image.room, "phash_hex": phash, "image_updated_at": mtime},
    )
    return phash


def similar_rooms(
    room: Room,
    top_k: int = _DEFAULT_TOP_K,
    max_distance: int = _DEFAULT_MAX_DISTANCE,
) -> list[tuple[Room, int]]:
    """Rooms whose primary photo looks like ``room``'s, nearest first.

    Returns ``[(room, hamming_distance), ...]`` — only rooms with a primary
    image that computed a hash and is within ``max_distance`` bits. The source
    room itself is excluded.
    """
    primary = room.images.filter(is_primary=True).first() or room.images.first()
    if primary is None:
        return []
    source_hash = _hash_for_image(primary)
    if source_hash is None:
        return []

    matches: list[tuple[Room, int]] = []
    # Evaluate every other room's primary photo lazily (hash + cache on first
    # use) — small dev datasets are instant; production would seed via a
    # management command instead of warming on first request.
    for other in Room.objects.exclude(pk=room.pk).prefetch_related("images"):
        other_primary = other.images.filter(is_primary=True).first() or other.images.first()
        if other_primary is None:
            continue
        other_hash = _hash_for_image(other_primary)
        if other_hash is None:
            continue
        distance = hamming_distance(source_hash, other_hash)
        if distance <= max_distance:
            matches.append((other, distance))

    matches.sort(key=lambda pair: pair[1])
    return matches[:top_k]
