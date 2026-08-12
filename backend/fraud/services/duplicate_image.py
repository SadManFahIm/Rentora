"""Cross-listing duplicate-image fraud detection (Phase 11 — Fraud Intelligence).

The scam-listing tell this catches: the *same* photo (or a visually
near-identical one) re-used across two different listings. A property
manager legitimately posting several rooms from one apartment is not fraud —
so severity is contextual, and this detector only ever emits a *risk signal*;
an admin decides.

Reuse over rebuild
------------------
- Perceptual hashing lives in ``rooms.image_search`` (64-bit average hash,
  cached in ``RoomImageHash`` keyed by file mtime). We call that — we do not
  hash a second way.
- Comparison uses Hamming distance over the cached hex hashes, with a cheap
  hex-prefix pre-filter so a scan never does an NxN full-table pass.
- Matching happens lazily per scan: the target room's images are hashed
  (and cached) on first scan; other rooms' hashes warm up as they get
  scanned (the daily catalogue re-scan covers every room within one cycle).

False-positive protection
-------------------------
- Images repeated *within the same listing* are never flagged (that's just a
  gallery with duplicates).
- Same-owner duplicates (agency / same property, multiple rooms) downgrade to
  ``low`` — a signal, not an accusation.
- Threshold and switch are configurable (``IMAGE_DUPLICATE_THRESHOLD``,
  ``DUPLICATE_IMAGE_FRAUD_ENABLED``).
"""

from __future__ import annotations

import logging

from django.conf import settings

from rooms.image_search import hamming_distance
from rooms.models import Room, RoomImage, RoomImageHash

from ..models import FraudReport, FraudSignal

logger = logging.getLogger(__name__)

# Hash prefix length used as a cheap pre-filter: two 64-bit average hashes
# that differ in <= IMAGE_DUPLICATE_THRESHOLD (default 8) of 64 bits almost
# always share their first 2 bytes, so only same-prefix candidates need the
# real Hamming comparison.
_PREFIX_LEN = 4  # 4 hex chars = 2 bytes

# How many distinct duplicate matches justify escalating severity.
_HIGH_MATCH_COUNT = 3


# A hash needs at least this many set bits to carry real structure; fewer
# means a blank/near-blank image whose "match" is meaningless.
_MIN_STRUCTURE_BITS = 4


def _low_structure(phash: str) -> bool:
    return bin(int(phash, 16)).count("1") < _MIN_STRUCTURE_BITS


def _hash_for_image(image: RoomImage) -> str | None:
    """Hash (and cache) one image via the shared pHash pipeline."""
    try:
        from rooms.image_search import _hash_for_image as cached_hash

        return cached_hash(image)
    except Exception as exc:  # pragma: no cover - best-effort, like the rest
        logger.warning("Duplicate-image scan could not hash image %s: %s", image.pk, exc)
    return None


# Cap on how many other rooms' primary images a single scan will warm
# (hash + cache) — protects a cold catalogue from a pathological first run.
# Cached hashes are free (mtime check only), so steady-state scans hit the
# cap's effect almost never.
WARM_CAP = 500


def _warm_primary_hashes(exclude_room_id: int) -> dict[int, str | None]:
    """Hash (and cache) primary images of other rooms that lack a cached hash.

    Returns ``{room_id: phash | None}``. Without this warm-up a freshly
    uploaded listing would never match a *previous* listing whose photo was
    never hashed yet (the two scans need each other's hashes to exist). One
    pass warms everything; later scans hit the cache and do no I/O.
    """
    warmed: dict[int, str | None] = {}
    already_hashed = set(RoomImageHash.objects.values_list("image_id", flat=True)[: WARM_CAP * 4])
    rooms = (
        Room.objects.exclude(pk=exclude_room_id)
        .filter(images__isnull=False)
        .distinct()
        .prefetch_related("images")[:WARM_CAP]
    )
    for room in rooms:
        primary = room.images.filter(is_primary=True).first() or room.images.first()
        if primary is None or primary.pk in already_hashed:
            continue
        warmed[room.pk] = _hash_for_image(primary)
    return warmed


def _candidate_index(exclude_room_id: int) -> dict[str, list[dict]]:
    """All other rooms' image hashes, indexed by hex prefix.

    Returns ``{prefix: [{"room_id", "owner_id", "area", "phash"}, ...]}`` —
    one batched query (plus the bounded warm-up above), so the per-room scan
    never N+1s.
    """
    _warm_primary_hashes(exclude_room_id)
    index: dict[str, list[dict]] = {}
    rows = (
        RoomImageHash.objects.select_related("room__owner")
        .exclude(room_id=exclude_room_id)
        .values("room_id", "room__owner_id", "room__area", "phash_hex")
    )
    for row in rows:
        prefix = row["phash_hex"][:_PREFIX_LEN]
        index.setdefault(prefix, []).append(
            {
                "room_id": row["room_id"],
                "owner_id": row["room__owner_id"],
                "area": row["room__area"],
                "phash": row["phash_hex"],
            }
        )
    return index


def find_duplicate_images(room: Room) -> list[dict]:
    """Cross-listing duplicate matches for ``room``'s images.

    Returns a list of dicts, one per *matched other room* (deduped):
    ``{"room_id", "owner_id", "area", "similarity"}``. Best-effort: rooms
    without readable/cached hashes are simply not compared.
    """
    images = list(room.images.all())
    if not images:
        return []

    threshold = getattr(settings, "IMAGE_DUPLICATE_THRESHOLD", 8)
    index = _candidate_index(exclude_room_id=room.pk)

    matches: dict[int, dict] = {}
    for image in images:
        phash = _hash_for_image(image)
        if not phash or _low_structure(phash):
            # Solid-colour / near-blank images hash to (almost) all-zero bits
            # and would match *every* other blank image — no signal, skip.
            continue
        prefix = phash[:_PREFIX_LEN]
        for candidate in index.get(prefix, []):
            if candidate["room_id"] == room.pk:
                continue
            distance = hamming_distance(phash, candidate["phash"])
            if distance <= threshold:
                matches.setdefault(
                    candidate["room_id"],
                    {
                        "room_id": candidate["room_id"],
                        "owner_id": candidate["owner_id"],
                        "area": candidate["area"],
                        "similarity": round(1.0 - distance / 64.0, 3),
                    },
                )
    return list(matches.values())


def duplicate_image_signal(room: Room):
    """Run the duplicate-image detector for ``room`` (called by run_scan).

    Returns a ``Signal`` dataclass (see fraud/services/detectors.py) or None
    when there is nothing to flag. Severity is contextual:

    - same owner only  -> LOW    (agency / same-property multi-room posts)
    - different owners -> MEDIUM (re-used photo across unrelated accounts)
    - 3+ distinct matches, or different owner *and* different area
                          -> HIGH
    """
    from .detectors import Signal

    if not getattr(settings, "DUPLICATE_IMAGE_FRAUD_ENABLED", True):
        return None

    total = Room.objects.count()
    min_listings = getattr(settings, "IMAGE_DUPLICATE_MIN_LISTINGS", 2)
    if total < min_listings:
        return None

    matches = find_duplicate_images(room)
    if not matches:
        return None

    matched_ids = [m["room_id"] for m in matches]
    same_owner_all = all(m["owner_id"] == room.owner_id for m in matches)
    different_area_any = any(m["area"] != room.area for m in matches)
    best_similarity = max(m["similarity"] for m in matches)

    if same_owner_all:
        severity = FraudReport.Severity.LOW
        message = (
            f"Same photo is used in {len(matches)} of your own listing(s) "
            f"({', '.join('#' + str(i) for i in matched_ids)}) — re-used images "
            "make tenants doubt the listing."
        )
    elif len(matches) >= _HIGH_MATCH_COUNT or different_area_any:
        severity = FraudReport.Severity.HIGH
        message = (
            f"Listing photo matches {len(matches)} other listing(s) "
            f"({', '.join('#' + str(i) for i in matched_ids[:6])}) "
            "from different owners/areas — a classic scam-listing pattern."
        )
    else:
        severity = FraudReport.Severity.MEDIUM
        message = (
            f"Listing photo is reused in {len(matches)} other listing(s) "
            f"({', '.join('#' + str(i) for i in matched_ids)}) "
            "from a different owner."
        )

    return Signal(
        detector=FraudSignal.Detector.DUPLICATE_IMAGE,
        severity=severity,
        message=message,
        detail={
            "matched_listing_ids": matched_ids,
            "similarity": best_similarity,
            "same_owner": same_owner_all,
            "same_area": not different_area_any,
            "owner_id": room.owner_id,
        },
    )
