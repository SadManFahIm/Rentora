"""Phase 12.5 — content moderation detectors.

Deterministic, cheap, metadata-only risk assessment for reviews and photos.
The photo side reuses the platform's pHash pipeline (``rooms.image_search``)
for duplicate detection — no second hashing implementation. Everything is
best-effort: unreadable files, external URLs and missing Pillow degrade to a
safe ``approved`` fast-path instead of an error, and every decision is
reversible by an admin.

Only *metadata* is ever stored in the moderation records (risk score,
detector keys, short labels) — never the review comment or photo bytes.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ModerationStatus, PhotoModeration, ReviewModeration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Review text detectors
# ---------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
# Bangla + English contact / spam pivots. Deliberately conservative: each
# match only adds score — a review needs several signals (or one strong one)
# to cross the flag threshold, so a normal user's honest review is safe.
_SPAM_PHRASES = [
    "check my profile",
    "visit my profile",
    "contact me",
    "dm me",
    "message me",
    "call me",
    "whatsapp",
    "telegram",
    "bkash",
    "nagad",
    "click here",
    "click the link",
    "earn money",
    "make money",
    "cash out",
    "send money",
    "pay outside",
]
# Bangladeshi mobile numbers: 01XXXXXXXXX or +8801XXXXXXXXX.
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?880|0)1[3-9]\d{8}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

_MIN_VOWELS_FOR_MEANING = 4  # a "comment" with fewer vowels is likely gibberish


def _signal(key: str, label: str, detail: dict | None = None) -> dict:
    return {"key": key, "label": label, **(detail or {})}


def score_review_text(review) -> tuple[int, list[dict]]:
    """Deterministic 0-100 risk + signal list for one review.

    Signals weigh differently (a link is stronger than shouting); the score is
    capped at 100. The decision (auto-approve vs moderation queue) is made by
    the caller against the configured threshold.
    """
    text = review.comment or ""
    signals: list[dict] = []
    score = 0

    urls = _URL_RE.findall(text)
    if urls:
        score += 30
        signals.append(_signal("contains_url", "Contains external link", {"count": len(urls)}))

    phones = _PHONE_RE.findall(text)
    if phones:
        score += 25
        signals.append(_signal("contact_info", "Contains phone number", {"count": len(phones)}))

    emails = _EMAIL_RE.findall(text)
    if emails:
        score += 25
        signals.append(_signal("contact_info", "Contains email address", {"count": len(emails)}))

    lower = text.lower()
    matched = [p for p in _SPAM_PHRASES if p in lower]
    if matched:
        score += 20 * min(len(matched), 3)
        signals.append(_signal("spam_phrase", "Spam-like phrasing", {"phrases": matched[:5]}))

    letters = [c for c in text if c.isalpha()]
    if letters and len(letters) > 12 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        score += 10
        signals.append(_signal("all_caps", "All-caps text"))
    if text.count("!") >= 5 or text.count("?") >= 5:
        score += 10
        signals.append(_signal("excessive_punctuation", "Excessive punctuation"))

    # Gibberish / near-empty comments.
    normalized = re.sub(r"[^a-z0-9\u0980-\u09ff]+", " ", lower).strip()
    vowel_count = sum(1 for ch in normalized if ch in "aeiou")
    if normalized and len(normalized) < 3:
        score += 15
        signals.append(_signal("too_short", "Too short to be useful"))
    elif len(text) >= 6 and vowel_count < _MIN_VOWELS_FOR_MEANING and not urls and not phones:
        score += 15
        signals.append(_signal("gibberish", "Unlikely meaningful text"))

    # Duplicate text: the same comment body posted by another user recently.
    if text.strip():
        from bookings.models import Review

        duplicate = (
            Review.objects.exclude(pk=review.pk)
            .filter(comment__iexact=text[:500])
            .filter(created_at__gte=timezone.now() - timedelta(days=90))
            .exclude(user_id=review.user_id)
            .exists()
        )
        if duplicate:
            score += 40
            signals.append(_signal("duplicate_text", "Same text posted by another user"))

    # Review velocity: many reviews from the same account in one hour.
    from bookings.models import Review

    velocity = (
        Review.objects.filter(user_id=review.user_id)
        .filter(created_at__gte=timezone.now() - timedelta(hours=1))
        .count()
    )
    if velocity >= 4:
        score += 25
        signals.append(
            _signal("review_velocity", "Unusually fast review posting", {"last_hour": velocity})
        )

    return min(score, 100), signals


def record_review_moderation(review) -> ReviewModeration | None:
    """Assess a review and persist its moderation record.

    Auto-approves low-risk reviews (fast path — public immediately); high-risk
    ones land in the admin queue as ``pending``. Returns the record, or
    ``None`` when moderation is disabled.
    """
    if not getattr(settings, "REVIEW_MODERATION_ENABLED", True):
        return None
    threshold = getattr(settings, "REVIEW_MODERATION_FLAG_THRESHOLD", 60)
    score, signals = score_review_text(review)
    status = ModerationStatus.PENDING if score >= threshold else ModerationStatus.APPROVED
    record, _ = ReviewModeration.objects.update_or_create(
        review=review,
        defaults={"risk_score": score, "signals": signals, "status": status},
    )
    return record


# ---------------------------------------------------------------
# Photo detectors (pHash reuse)
# ---------------------------------------------------------------


def _phash_for_listing_image(image) -> str | None:
    """pHash for one RoomImage, deliberately *uncached*.

    Moderation must not write ``RoomImageHash`` rows for the photo being
    assessed: the fraud engine owns that cache and relies on it staying empty
    until a scan lazily warms it (see fraud/services/duplicate_image.py).
    We read the cache (via :func:`duplicate_matches`) but never extend it
    with the source image.
    """
    try:
        from pathlib import Path

        from PIL import Image

        from rooms.image_search import average_hash

        with Image.open(Path(image.image.path)) as img:
            return average_hash(img)
    except Exception as exc:  # pragma: no cover - best-effort
        logger.warning("Photo moderation could not hash image %s: %s", image.pk, exc)
    return None


_WARM_CAP = 200


def _warm_primary_hashes(exclude_image) -> None:
    """Hash (and cache) primary images of other rooms lacking a cached hash.

    Mirrors the fraud engine's warm-up pass: moderation's duplicate check
    needs earlier listings' photos in ``RoomImageHash`` to compare against,
    but those hashes are created lazily (only when a scan or this warm-up
    runs). One bounded pass per upload keeps the check real without touching
    the source image's own cache row.
    """
    from rooms.models import Room, RoomImageHash

    already = set(RoomImageHash.objects.values_list("image_id", flat=True))
    rooms = (
        Room.objects.exclude(pk=exclude_image.room_id)
        .filter(images__isnull=False)
        .distinct()
        .prefetch_related("images")[:_WARM_CAP]
    )
    for room in rooms:
        primary = room.images.filter(is_primary=True).first() or room.images.first()
        if primary is None or primary.pk in already:
            continue
        try:
            from rooms.image_search import _hash_for_image

            _hash_for_image(primary)
        except Exception:  # pragma: no cover - best-effort
            continue


def _phash_for_url(url: str) -> str | None:
    """Best-effort pHash for a *local* media URL (review photos).

    External http(s) URLs are deliberately not fetched during moderation —
    downloading remote content server-side is a security/SSRF surface, so
    those photos simply skip the duplicate check (graceful degradation).
    """
    from pathlib import Path
    from urllib.parse import urlparse

    from django.conf import settings as dj_settings

    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        return None
    path = parsed.path
    if path.startswith(dj_settings.MEDIA_URL):
        path = path[len(dj_settings.MEDIA_URL) :]
    full = Path(dj_settings.MEDIA_ROOT) / path.lstrip("/")
    if not full.exists():
        return None
    try:
        from PIL import Image

        from rooms.image_search import average_hash

        with Image.open(full) as img:
            return average_hash(img)
    except Exception as exc:  # pragma: no cover - best-effort
        logger.warning("Photo moderation could not hash %s: %s", url, exc)
    return None


_PREFIX_LEN = 4  # 4 hex chars = 2 bytes — cheap same-prefix pre-filter
# A hash needs at least this many set bits to carry real structure; fewer
# means a blank/near-blank image whose "match" is meaningless (a solid colour
# photo would otherwise "duplicate" every other solid colour photo).
_MIN_STRUCTURE_BITS = 4


def _low_structure(phash: str) -> bool:
    return bin(int(phash, 16)).count("1") < _MIN_STRUCTURE_BITS


def duplicate_matches(phash: str | None, exclude_room_id: int | None = None) -> list[dict]:
    """Rooms whose cached primary-image hash is within threshold of ``phash``.

    Returns ``[{"room_id", "title"}, ...]`` (max 5) — the evidence an admin
    sees in the moderation queue. ``exclude_room_id`` skips the source room's
    own cached hash (a photo must not "duplicate itself"). Empty for
    unhashable / blank images.
    """
    from rooms.image_search import hamming_distance
    from rooms.models import RoomImageHash

    if not phash or _low_structure(phash):
        return []
    threshold = getattr(settings, "IMAGE_DUPLICATE_THRESHOLD", 8)
    matches = []
    for row in (
        RoomImageHash.objects.filter(phash_hex__startswith=phash[:_PREFIX_LEN])
        .select_related("room")
        .values("room_id", "room__title", "phash_hex")
    ):
        if row["room_id"] == exclude_room_id:
            continue
        if hamming_distance(phash, row["phash_hex"]) <= threshold:
            matches.append({"room_id": row["room_id"], "title": row["room__title"]})
    return matches[:5]


def record_listing_photo_moderation(image) -> PhotoModeration | None:
    """Assess a listing photo (RoomImage post-save hook).

    A photo that duplicates another listing's cached hash is flagged for the
    admin queue; otherwise it is auto-approved. An admin decision is never
    silently undone by a re-save (approved stays approved).
    """
    if not getattr(settings, "PHOTO_MODERATION_ENABLED", True):
        return None
    # Warm other listings' hashes into the cache (lazily created on demand),
    # then compute this photo's own hash WITHOUT caching it.
    _warm_primary_hashes(image)
    phash = _phash_for_listing_image(image)
    matches = duplicate_matches(phash, exclude_room_id=image.room_id)

    score = 40 if matches else 0
    signals = (
        [
            _signal(
                "duplicate_image",
                "Visually similar to another listing's photo",
                {"matches": matches},
            )
        ]
        if matches
        else []
    )
    status = ModerationStatus.PENDING if matches else ModerationStatus.APPROVED

    record, created = PhotoModeration.objects.get_or_create(
        image=image,
        defaults={
            "target_type": PhotoModeration.TargetType.LISTING,
            "room": image.room,
            "image_url": image.image.url,
            "uploaded_by": image.room.owner,
            "phash": phash or "",
            "risk_score": score,
            "signals": signals,
            "status": status,
        },
    )
    # Re-saves only ever *add* evidence — never downgrade an admin-approved
    # photo back into the queue.
    if not created and record.status != ModerationStatus.APPROVED and score > record.risk_score:
        record.risk_score = score
        record.signals = signals
        record.save(update_fields=["risk_score", "signals"])
    return record


def record_review_photo_moderation(review, url: str, uploaded_by) -> PhotoModeration | None:
    """Assess one review photo (URL string) — best-effort duplicate check."""
    if not getattr(settings, "PHOTO_MODERATION_ENABLED", True):
        return None
    phash = _phash_for_url(url)
    matches = duplicate_matches(phash) if phash else []

    score = 40 if matches else 0
    signals = (
        [
            _signal(
                "duplicate_image",
                "Visually similar to another listing's photo",
                {"matches": matches},
            )
        ]
        if matches
        else []
    )
    status = ModerationStatus.PENDING if matches else ModerationStatus.APPROVED

    record, _ = PhotoModeration.objects.get_or_create(
        review=review,
        image_url=url,
        defaults={
            "target_type": PhotoModeration.TargetType.REVIEW,
            "uploaded_by": uploaded_by,
            "phash": phash or "",
            "risk_score": score,
            "signals": signals,
            "status": status,
        },
    )
    return record
