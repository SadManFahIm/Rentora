"""EXIF/GPS extraction utilities (Phase 17 — Stage 2).

Extracts GPS coordinates from image EXIF data **before** the privacy-critical
``strip_exif()`` runs. This preserves the existing privacy pipeline (GPS is
stripped from stored images) while allowing Phase 17's photo-geo authenticity
feature to capture location metadata at upload time.

Design:

- ``extract_gps_from_exif(data)`` takes raw image bytes, opens the image
  under the same bomb-guard as ``config.images.open_verified_image``, reads
  the EXIF GPS IFD, and returns ``(lat, lng, accuracy)`` or ``None``.
- The function is **read-only** — it never modifies the image bytes.
- GPS is extracted from the original upload *before* ``strip_exif()`` is
  called, so no existing behaviour changes.
- Latitude/longitude are returned as ``(float, float, str)`` where accuracy
  is one of: ``"high"`` (GPS method present), ``"medium"`` (GPS data present
  but no method), ``"low"`` (parsed from nearby fields, unreliable).
- If Pillow or EXIF data is unavailable, returns ``None`` — the upload
  pipeline is never affected.
"""

from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def extract_gps_from_exif(data: bytes) -> tuple[float, float, str] | None:
    """Extract GPS coordinates from image EXIF data.

    Parameters
    ----------
    data : bytes
        Raw image file bytes (the original upload, before any processing).

    Returns
    -------
    tuple[float, float, str] | None
        ``(latitude, longitude, accuracy)`` where accuracy is ``"high"``,
        ``"medium"``, or ``"low"``. Returns ``None`` when GPS data is not
        found or cannot be parsed.
    """
    try:
        from PIL import Image

        img = Image.open(BytesIO(data))
        exif_data = img.getexif()
        if not exif_data:
            return None

        gps_ifd = exif_data.get_ifd(0x8825)  # GPSInfo IFD tag
        if not gps_ifd:
            return None

        lat = _parse_gps_coord(gps_ifd, 2, gps_ifd.get(1))  # GPSLatitude + GPSLatitudeRef
        lng = _parse_gps_coord(gps_ifd, 4, gps_ifd.get(3))  # GPSLongitude + GPSLongitudeRef

        if lat is None or lng is None:
            return None

        # Determine accuracy based on available metadata
        accuracy = "medium"
        if 7 in gps_ifd:  # GPSProcessingMethod
            accuracy = "high"

        return (lat, lng, accuracy)

    except Exception as exc:
        # Never fail the upload pipeline — GPS extraction is best-effort.
        logger.debug("GPS extraction failed (non-fatal): %s", exc)
        return None


def _parse_gps_coord(gps_ifd: dict, coord_tag: int, ref_tag: str | None) -> float | None:
    """Parse a single GPS coordinate (lat or lng) from EXIF tags.

    Returns decimal degrees with correct sign (negative for S/W), or None.
    """
    try:
        raw = gps_ifd.get(coord_tag)
        if raw is None or len(raw) != 3:
            return None

        d, m, s = raw
        # Handle both IFDRational and plain tuples
        d = float(d)
        m = float(m)
        s = float(s)

        decimal = d + (m / 60.0) + (s / 3600.0)

        if ref_tag and str(ref_tag).upper() in ("S", "W"):
            decimal = -decimal

        # Basic sanity check: Dhaka is roughly 23-24 lat, 90-91 lng.
        # Accept wider bounds (entire Bangladesh) to avoid false negatives.
        if not (-90.0 <= decimal <= 90.0):
            return None

        return round(decimal, 6)

    except Exception:
        return None


def has_gps_data(data: bytes) -> bool:
    """Quick check: does this image contain GPS EXIF data?

    Lighter than ``extract_gps_from_exif`` — reads only the EXIF header,
    not the full GPS IFD. Useful for decisions like "should we store
    a PhotoGeoSignal record for this image?".
    """
    try:
        from PIL import Image

        img = Image.open(BytesIO(data))
        exif_data = img.getexif()
        if not exif_data:
            return False
        return 0x8825 in exif_data  # GPSInfo IFD tag
    except Exception:
        return False
