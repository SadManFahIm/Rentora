"""Photo-Geo Authenticity detector (Phase 17, Stage 5).

Compares GPS coordinates embedded in uploaded room photos against the room's
declared lat/lng to detect stock-photo or stolen-image fraud. When a photo's
GPS location is significantly far from the room's declared area, a
``photo_geo_mismatch`` FraudSignal is created.

Design:
- GPS is extracted from the original upload *before* ``strip_exif()`` runs
  (see ``config/exif_utils.py``). RoomImage stores the extracted coordinates.
- Distance is computed using ``config.trust_utils.compute_haversine_distance``.
- A configurable threshold (``PHOTO_GEO_MISMATCH_THRESHOLD_KM``, default 5 km)
  determines when a mismatch is flagged — Dhaka's metro area is ~30 km wide,
  so 5 km catches out-of-city stock photos while allowing nearby-area noise.
- The detector is feature-flagged via ``phase17.photo_geo``.
"""

from __future__ import annotations

import logging

from django.conf import settings

from config.trust_utils import compute_haversine_distance
from fraud.models import FraudReport, FraudSignal

logger = logging.getLogger(__name__)

# Default threshold: 5 km — catches stock photos from other cities/countries
# while allowing typical Dhaka neighborhood GPS drift.
DEFAULT_THRESHOLD_KM = 5.0


def get_threshold_km() -> float:
    return getattr(settings, "PHOTO_GEO_MISMATCH_THRESHOLD_KM", DEFAULT_THRESHOLD_KM)


def extract_gps_for_room_image(room_image) -> tuple[float, float, str] | None:
    """Extract GPS from a RoomImage's file and store it on the model.

    Called at upload time (before strip_exif). Returns (lat, lng, accuracy)
    or None if no GPS data found. Side effect: updates photo_lat/photo_lng
    on the RoomImage instance (caller must save).
    """
    from config.exif_utils import extract_gps_from_exif

    if not room_image.image:
        return None

    try:
        with open(room_image.image.path, "rb") as fh:
            data = fh.read(5 * 1024 * 1024)  # read up to 5 MB
    except (OSError, ValueError):
        return None

    result = extract_gps_from_exif(data)
    if result is None:
        return None

    lat, lng, accuracy = result
    room_image.photo_lat = lat
    room_image.photo_lng = lng
    room_image.photo_gps_accuracy = accuracy
    return (lat, lng, accuracy)


def check_photo_geo_mismatch(room) -> dict:
    """Check all photos of a room against its declared lat/lng.

    Returns:
        {
            "mismatch": bool,
            "max_distance_km": float | None,
            "mismatched_images": [...],
            "threshold_km": float,
        }
    """
    threshold = get_threshold_km()
    room_lat = float(room.lat) if room.lat is not None else None
    room_lng = float(room.lng) if room.lng is not None else None

    if room_lat is None or room_lng is None:
        return {
            "mismatch": False,
            "max_distance_km": None,
            "mismatched_images": [],
            "threshold_km": threshold,
        }

    mismatched = []
    max_dist = 0.0

    for img in room.images.filter(photo_lat__isnull=False).select_related():
        photo_lat = float(img.photo_lat)
        photo_lng = float(img.photo_lng)
        distance_m = compute_haversine_distance(room_lat, room_lng, photo_lat, photo_lng)
        distance_km = distance_m / 1000.0
        max_dist = max(max_dist, distance_km)

        if distance_km > threshold:
            mismatched.append(
                {
                    "image_id": img.pk,
                    "photo_lat": photo_lat,
                    "photo_lng": photo_lng,
                    "distance_km": round(distance_km, 2),
                    "accuracy": img.photo_gps_accuracy,
                }
            )

    return {
        "mismatch": len(mismatched) > 0,
        "max_distance_km": round(max_dist, 2),
        "mismatched_images": mismatched,
        "threshold_km": threshold,
    }


def create_photo_geo_signal(room, mismatch_result: dict) -> FraudSignal | None:
    """Create a FraudSignal for photo-geo mismatch if applicable.

    Returns the created signal, or None if no mismatch or if a signal
    already exists for this room.
    """
    if not mismatch_result["mismatch"]:
        return None

    # Don't duplicate signals
    existing = FraudSignal.objects.filter(
        report__room=room,
        detector=FraudSignal.Detector.PHOTO_GEO_MISMATCH,
    ).exists()
    if existing:
        return None

    # Get or create FraudReport
    report, _created = FraudReport.objects.get_or_create(
        room=room,
        defaults={"severity": FraudReport.Severity.LOW},
    )

    max_dist = mismatch_result["max_distance_km"]
    mismatched_count = len(mismatch_result["mismatched_images"])

    # Score: 40 base + 5 per mismatched image, capped at 80
    score = min(80, 40 + (mismatched_count * 5))

    if score >= 70:
        severity = FraudReport.Severity.HIGH
    elif score >= 50:
        severity = FraudReport.Severity.MEDIUM
    else:
        severity = FraudReport.Severity.LOW

    signal = FraudSignal.objects.create(
        report=report,
        detector=FraudSignal.Detector.PHOTO_GEO_MISMATCH,
        severity=severity,
        message=(
            f"Photo-geo mismatch: {mismatched_count} image(s) are "
            f">{max_dist}km from the declared location."
        ),
        detail={
            "max_distance_km": max_dist,
            "mismatched_images": mismatched_count,
            "threshold_km": mismatch_result["threshold_km"],
            "images": mismatch_result["mismatched_images"],
            "score": score,
        },
    )

    # Update report severity
    report.severity = severity
    report.score = max(report.score, score)
    report.summary = (
        f"Photo-geo mismatch: {mismatched_count} image(s) are "
        f">{max_dist}km from the declared location."
    )
    report.save(update_fields=["severity", "score", "summary"])

    logger.warning(
        "Photo-geo mismatch detected for room %s: %d images, max %.1f km",
        room.pk,
        mismatched_count,
        max_dist,
    )

    return signal


def scan_room_photo_geo(room) -> dict:
    """Full scan: check photos, create signal if mismatch found.

    Returns the scan result dict.
    """
    result = check_photo_geo_mismatch(room)
    if result["mismatch"]:
        create_photo_geo_signal(room, result)
    return result
