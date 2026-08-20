"""Fraud-detection engine.

Each detector is a pure function ``(room) -> Signal | None`` where Signal is
a small dataclass (detector key, severity, human message, machine detail).
``run_scan`` runs every detector, persists a ``FraudReport`` + ``FraudSignal``
rows, and derives the room's aggregate score/severity.

Severity weights
----------------
- high    : 100 points
- medium  : 60  points
- low     : 25  points

Score is capped at 100. Severity of the *report* is derived from the max
signal severity, not the raw score, so one high-risk signal (e.g. a clear
duplicate) can never be hidden by "only one issue".
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from rooms.models import Room

from ..models import FraudReport, FraudSignal

logger = logging.getLogger(__name__)

# Price-anomaly thresholds vs the (area, room_type) market segment:
# below 60% of the 25th percentile is "too good to be true", above 150% of
# the 75th percentile is "priced to fleece".
PRICE_LOW_FACTOR = 0.60
PRICE_HIGH_FACTOR = 1.50

# Duplicate / similarity thresholds (difflib ratio, 0..1).
DUPLICATE_TITLE_RATIO = 0.85
DESCRIPTION_SIMILARITY_RATIO = 0.80

# A landlord who publishes this many rooms inside one day is signalling
# volume-account spam rather than genuine individual listings.
RAPID_LISTING_MAX_PER_DAY = 3

WEIGHTS = {"high": 100, "medium": 60, "low": 25}


@dataclass
class Signal:
    detector: str
    severity: str
    message: str
    detail: dict = field(default_factory=dict)


def _suspicious_price(room: Room) -> Signal | None:
    """Compare the room's price against its (area, room_type) market segment.

    Uses the same ``MarketStat`` snapshot the pricing insight feature reads,
    so pricing and fraud always agree on what "normal" is.
    """
    try:
        from pricing.models import MarketStat
    except ImportError:
        return None

    try:
        stat = MarketStat.objects.get(area=room.area, room_type=room.room_type)
    except MarketStat.DoesNotExist:
        return None

    if stat.sample_size < 3:
        return None

    p25, p75 = float(stat.percentile_25), float(stat.percentile_75)
    price = float(room.price)

    if price < p25 * PRICE_LOW_FACTOR:
        return Signal(
            detector=FraudSignal.Detector.SUSPICIOUS_PRICE,
            severity=FraudReport.Severity.MEDIUM,
            message=(
                f"Price ({price:,.0f} BDT) is well below the {room.get_area_display()} "
                f"{room.get_room_type_display()} market ({p25:,.0f} BDT 25th percentile) — "
                "possibly a bait listing."
            ),
            detail={
                "price": price,
                "percentile_25": p25,
                "market": stat.area,
                "room_type": stat.room_type,
            },
        )
    if price > p75 * PRICE_HIGH_FACTOR:
        return Signal(
            detector=FraudSignal.Detector.SUSPICIOUS_PRICE,
            severity=FraudReport.Severity.LOW,
            message=(
                f"Price ({price:,.0f} BDT) is far above the {room.get_area_display()} "
                f"{room.get_room_type_display()} market ({p75:,.0f} BDT 75th percentile)."
            ),
            detail={
                "price": price,
                "percentile_75": p75,
                "market": stat.area,
                "room_type": stat.room_type,
            },
        )
    return None


def _duplicate_listing(room: Room) -> Signal | None:
    """Flag rooms whose title is near-identical to another listing in the same area."""
    candidates = (
        Room.objects.filter(area=room.area).exclude(pk=room.pk).values_list("pk", "title", "price")
    )
    for other_id, other_title, _other_price in candidates:
        ratio = difflib.SequenceMatcher(None, room.title.lower(), other_title.lower()).ratio()
        if ratio >= DUPLICATE_TITLE_RATIO:
            return Signal(
                detector=FraudSignal.Detector.DUPLICATE_LISTING,
                severity=FraudReport.Severity.HIGH,
                message=(
                    f"Title is {ratio:.0%} similar to listing #{other_id} "
                    f"('{other_title}') in the same area."
                ),
                detail={
                    "similar_room_id": other_id,
                    "similar_room_title": other_title,
                    "similarity": round(ratio, 3),
                },
            )
    return None


def _description_similarity(room: Room) -> Signal | None:
    """Flag descriptions copied verbatim from another listing."""
    if not room.description.strip():
        return None
    candidates = (
        Room.objects.filter(area=room.area)
        .exclude(pk=room.pk)
        .exclude(description="")
        .values_list("pk", "description")
    )
    for other_id, other_description in candidates:
        ratio = difflib.SequenceMatcher(
            None, room.description.lower(), other_description.lower()
        ).ratio()
        if ratio >= DESCRIPTION_SIMILARITY_RATIO:
            return Signal(
                detector=FraudSignal.Detector.DESCRIPTION_SIMILARITY,
                severity=FraudReport.Severity.MEDIUM,
                message=(
                    f"Description is {ratio:.0%} identical to listing #{other_id} — "
                    "looks copied, not original."
                ),
                detail={"similar_room_id": other_id, "similarity": round(ratio, 3)},
            )
    return None


def _missing_images(room: Room) -> Signal | None:
    """A room listing with zero images is either unfinished or fake."""
    if room.images.count() == 0:
        return Signal(
            detector=FraudSignal.Detector.MISSING_IMAGES,
            severity=FraudReport.Severity.LOW,
            message="Listing has no images — tenants can't verify what they're paying for.",
            detail={"image_count": 0},
        )
    return None


def _unverified_owner(room: Room) -> Signal | None:
    """Listings from unverified landlords carry more risk."""
    if room.owner and not room.owner.nid_verified:
        return Signal(
            detector=FraudSignal.Detector.UNVERIFIED_OWNER,
            severity=FraudReport.Severity.LOW,
            message="Owner has not completed NID verification.",
            detail={"owner_id": room.owner_id, "nid_verified": False},
        )
    return None


def _rapid_listing(room: Room) -> Signal | None:
    """Same owner publishing many rooms in a short window."""
    since = timezone.now() - timedelta(days=1)
    count = Room.objects.filter(owner=room.owner, created_at__gte=since).count()
    if count > RAPID_LISTING_MAX_PER_DAY:
        return Signal(
            detector=FraudSignal.Detector.RAPID_LISTING,
            severity=FraudReport.Severity.MEDIUM,
            message=f"Owner published {count} listings within 24 hours.",
            detail={"rooms_in_24h": count},
        )
    return None


def _fraud_ring(room: Room) -> Signal | None:
    """Flag listings whose owner belongs to a coordinated-account ring (Phase 15, D8).

    Reuses the ring graph from ``fraud.services.rings``: a shared phone with
    another account (strong) or a shared audit IP + same-area listings (weak)
    links the owner to a ring. Severity follows the link strength; the detail
    carries the evidence for the admin reviewer. Review aid, never a block.
    """
    from .rings import owner_ring_membership

    membership = owner_ring_membership(room.owner)
    if membership is None:
        return None
    severity = (
        FraudReport.Severity.MEDIUM
        if membership["strength"] == "strong"
        else FraudReport.Severity.LOW
    )
    return Signal(
        detector=FraudSignal.Detector.FRAUD_RING,
        severity=severity,
        message=(
            f"Owner is linked to a {membership['member_count']}-account ring "
            f"({membership['evidence']}). Review the accounts before trusting this listing."
        ),
        detail={
            "member_count": membership["member_count"],
            "strength": membership["strength"],
            "evidence": membership["evidence"],
            "peer_user_ids": membership["peers"],
        },
    )


# The duplicate-image detector lives in its own module (it reuses the pHash
# pipeline from rooms/image_search.py) and is imported here — at module level
# it is a one-way dependency (duplicate_image only imports back lazily inside
# its function), so there is no circular import.
from .duplicate_image import duplicate_image_signal

# Photo-forensics detector (Tier 2): ELA / watermark / low-quality signals on
# the listing's own images. Imported at module level the same way as
# duplicate_image (it imports RoomImage lazily inside its function).
from .image_forensics import analyze_image


def _image_forensics(room: Room) -> Signal | None:
    """Flag listing photos that show signs of manipulation (ELA inconsistency,
    watermark overlay, editor software) or are too small to be real photos.

    Reads at most the first 8 images and treats any unreadable/missing file
    as 'no signal' — the scan must never fail a listing because of one bad
    file. Severity: medium for a likely manipulation, low otherwise.
    """

    images = list(room.images.all()[:8])
    findings: list[dict] = []
    worst: str | None = None
    for image in images:
        try:
            path = image.image.path
        except Exception:
            continue
        import os

        if not os.path.exists(path):
            continue
        try:
            result = analyze_image(path)
        except Exception:
            logger.exception("image forensics failed for image %s", image.pk)
            continue
        if not result.signals:
            continue
        findings.append(
            {
                "image_id": image.pk,
                "signals": [s.as_dict() for s in result.signals],
                "ela_mean": result.ela_mean,
                "ela_p99": result.ela_p99,
            }
        )
        if result.worst_severity and (worst is None or result.worst_severity == "medium"):
            worst = result.worst_severity

    if not findings:
        return None
    severity = FraudReport.Severity.MEDIUM if worst == "medium" else FraudReport.Severity.LOW
    return Signal(
        detector=FraudSignal.Detector.MANIPULATED_IMAGE,
        severity=severity,
        message=(
            "Listing photos show possible manipulation or watermarking — "
            f"{len(findings)} image(s) flagged for review."
        ),
        detail={"images": findings},
    )


DETECTORS: list[Callable[[Room], Signal | None]] = [
    _duplicate_listing,
    _description_similarity,
    _suspicious_price,
    _missing_images,
    _unverified_owner,
    _rapid_listing,
    _fraud_ring,
    duplicate_image_signal,
    _image_forensics,
]


def _score_signals(signals: list[Signal]) -> int:
    return min(100, sum(WEIGHTS.get(s.severity, 0) for s in signals))


def _severity_of(signals: list[Signal]) -> str:
    if not signals:
        return FraudReport.Severity.CLEAN
    order = [FraudReport.Severity.HIGH, FraudReport.Severity.MEDIUM, FraudReport.Severity.LOW]
    return next(
        (sev for sev in order if any(s.severity == sev for s in signals)),
        FraudReport.Severity.CLEAN,
    )


def _summary(signals: list[Signal], score: int) -> str:
    if not signals:
        return "No risk signals detected."
    labels = [FraudSignal.Detector(s.detector).label for s in signals]
    return f"Risk score {score}/100. Signals: {', '.join(labels)}."


def run_scan(room: Room) -> FraudReport:
    """Run every detector on ``room`` and persist a fresh report.

    Idempotent: the room's existing ``FraudReport`` (and its signals) is
    replaced wholesale, so a re-scan after the landlord fixes an issue
    reflects the new state.

    Detector failures are isolated: one detector raising (e.g. a transient
    DB error) never aborts the whole scan — it is logged and the remaining
    detectors still run, so a scan always produces a report.
    """
    signals: list[Signal] = []
    for detector in DETECTORS:
        try:
            signal = detector(room)
        except Exception:
            logger.exception(
                "Fraud detector %s failed for room %s; skipping it.",
                detector.__name__,
                room.pk,
            )
            continue
        if signal is not None:
            signals.append(signal)

    score = _score_signals(signals)
    severity = _severity_of(signals)

    report, _created = FraudReport.objects.get_or_create(room=room)
    report.signals.all().delete()
    report.severity = severity
    report.score = score
    report.summary = _summary(signals, score)
    report.save()

    FraudSignal.objects.bulk_create(
        [
            FraudSignal(
                report=report,
                detector=s.detector,
                severity=s.severity,
                message=s.message,
                detail=s.detail,
            )
            for s in signals
        ]
    )
    return report
