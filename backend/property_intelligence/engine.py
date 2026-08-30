"""Property Intelligence engine — collects existing signals, scores, caches.

One compute read a handful of small indexed queries (room + owner + images,
market stats, fraud report, 30-day demand counts, area demand). Results are
cached under ``property-intelligence:{room_id}:{config_signature}`` through
the hardening helpers in ``config.cache_utils``, so a Redis outage degrades
to recomputation instead of an error.

Privacy model: the *full* result (including staff provenance) is cached, but
only the public projection leaves this module for non-staff callers. Raw
fraud scores, graph IDs and KYC details are never returned there.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from config.cache_utils import safe_cache_get, safe_cache_set

from . import scoring
from .scoring import DISCLAIMER, SCORE_VERSION

_PHOTO_ANOMALY_DETECTORS = {
    "duplicate_image",
    "manipulated_image",
    "photo_geo_mismatch",
}

# Public payload keys — everything else (``provenance``, ``_engine``) is staff-only.
_PUBLIC_KEYS = (
    "room_id",
    "score",
    "confidence",
    "confidence_reasons",
    "score_version",
    "computed_at",
    "breakdown",
    "strengths",
    "suggestions",
    "data_freshness",
    "disclaimer",
)


def _config() -> dict[str, Any]:
    enabled = getattr(settings, "PROPERTY_INTELLIGENCE_ENABLED", True)
    weights = scoring.resolve_weights(getattr(settings, "PROPERTY_INTELLIGENCE_WEIGHTS", None))
    stale_days = int(getattr(settings, "PROPERTY_INTELLIGENCE_STALE_DAYS", 90))
    ttl = int(getattr(settings, "PROPERTY_INTELLIGENCE_CACHE_TTL_SECONDS", 900))
    quality_enabled = getattr(settings, "LISTING_QUALITY_SCORE_ENABLED", True)
    return {
        "enabled": enabled,
        "weights": weights,
        "stale_days": stale_days,
        "ttl": ttl,
        "quality_enabled": quality_enabled,
    }


def _get_fraud_report(room):
    # Direct query (not the reverse descriptor) so the engine is immune to
    # descriptor caching and never has to swallow DoesNotExist gymnastics.
    from fraud.models import FraudReport

    return FraudReport.objects.filter(room_id=room.pk).first()


def _collect(room, weights: dict[str, float], stale_days: int) -> dict[str, Any]:
    """Fetch every source signal once and shape it for scoring + provenance."""

    from bookings.models import Booking
    from pricing.models import MarketStat
    from pricing.services.insight import get_price_insight
    from rooms.geo import haversine_km
    from rooms.listing_quality import get_listing_quality
    from rooms.map_intel import _area_demand, metro_access_score
    from rooms.models import RoomView
    from wishlist.models import Wishlist

    market = MarketStat.objects.filter(area=room.area, room_type=room.room_type).first()
    insight = get_price_insight(room)
    report = _get_fraud_report(room)
    signals = list(report.signals.all()) if report is not None else []
    images = list(room.images.all())

    now = timezone.now()
    since = now - timedelta(days=30)
    views_30d = RoomView.objects.filter(room=room, viewed_at__gte=since).count()
    saves_30d = Wishlist.objects.filter(room=room, created_at__gte=since).count()
    requests_30d = Booking.objects.filter(room=room, created_at__gte=since).count()
    area = _area_demand(room.area)

    quality = get_listing_quality(room)
    quality_score = quality.get("score")
    quality_available = bool(
        getattr(settings, "LISTING_QUALITY_SCORE_ENABLED", True) and quality_score is not None
    )

    anomalies = [
        {"detector": s.detector, "severity": s.severity}
        for s in signals
        if s.detector in _PHOTO_ANOMALY_DETECTORS
    ]

    moderation_risk = 0
    try:
        for mod in room.photo_moderations.all():
            moderation_risk = max(moderation_risk, int(mod.risk_score or 0))
    except Exception:
        moderation_risk = 0

    has_geo = float(room.lat or 0) != 0 and float(room.lng or 0) != 0
    gps_consistent, gps_accuracy = False, ""
    if has_geo:
        for img in images:
            if img.photo_lat is not None and img.photo_lng is not None:
                distance = haversine_km(
                    float(room.lat), float(room.lng), float(img.photo_lat), float(img.photo_lng)
                )
                if distance <= scoring._GEO_CONSISTENT_KM:
                    gps_consistent = True
                gps_accuracy = img.photo_gps_accuracy or gps_accuracy

    data = {
        "listing_quality": {
            "score": quality_score,
            "available": quality_available,
            "level": quality.get("level"),
        },
        "price": {
            "available": insight is not None,
            "classification": insight.get("classification") if insight else None,
            "message": insight.get("message") if insight else "",
            "sample_size": insight.get("sample_size") if insight else 0,
        },
        "location": {
            "available": has_geo,
            "metro_score": metro_access_score(float(room.lat), float(room.lng)) if has_geo else 0,
        },
        "photos": {
            "count": len(images),
            "has_primary": any(img.is_primary for img in images),
            "anomalies": [(a["detector"], a["severity"]) for a in anomalies],
            "moderation_risk": moderation_risk,
            "gps_consistent": gps_consistent,
        },
        "trust": {
            "verified": bool(room.verified),
            "nid_verified": bool(room.owner.nid_verified),
            "tenant_verified": bool(room.owner.tenant_verified),
            "fraud": (
                {"exists": True, "severity": report.severity}
                if report is not None
                else {"exists": False}
            ),
        },
        "demand": {
            "own": {"views": views_30d, "saves": saves_30d, "requests": requests_30d},
            "area": {
                "score": area.get("score"),
                "total_signals": (
                    area.get("views_30d", 0)
                    + area.get("saves_30d", 0)
                    + area.get("bookings_30d", 0)
                ),
                "listings": area.get("listings", 0),
                "label": area.get("label"),
            },
            "available": False,  # fixed below by the real demand scorer
        },
        "quality_suggestions": list(quality.get("suggestions") or []),
        "stale_days": (now.date() - room.updated_at.date()).days if room.updated_at else 0,
        "stale_threshold_days": stale_days,
        "freshness": {
            "room": room.updated_at.isoformat() if room.updated_at else None,
            "market": market.calculated_at.isoformat() if market else None,
            "fraud": report.updated_at.isoformat() if report else None,
            "photos": (max((i.created_at for i in images), default=None)).isoformat()
            if images
            else None,
            "demand": now.isoformat(),
        },
        "provenance": {
            "market": _market_provenance(market),
            "price": (
                {
                    "classification": insight["classification"],
                    "percentage_diff": insight["percentage_diff"],
                    "message": insight["message"],
                }
                if insight
                else None
            ),
            "fraud": (
                {
                    "report_exists": True,
                    "severity": report.severity,
                    "status": report.status,
                    "risk_score": report.score,
                    "detector_names": [s.detector for s in signals],
                    "updated_at": report.updated_at.isoformat() if report.updated_at else None,
                }
                if report
                else {"report_exists": False}
            ),
            "verification": {
                "room_verified": bool(room.verified),
                "nid_verified": bool(room.owner.nid_verified),
                "tenant_verified": bool(room.owner.tenant_verified),
                "owner_id": room.owner_id,
            },
            "photos": {
                "count": len(images),
                "has_primary": any(img.is_primary for img in images),
                "gps_accuracy": gps_accuracy,
                "anomalies": anomalies,
                "moderation_risk": moderation_risk,
                "gps_consistent": gps_consistent,
            },
            "demand": {
                "views_30d": views_30d,
                "saves_30d": saves_30d,
                "requests_30d": requests_30d,
                "own_engagement": views_30d + saves_30d * 3 + requests_30d * 6,
                "area": area,
            },
        },
    }
    # Resolve demand availability exactly as the scorer would.
    _, demand_available, _ = scoring.score_demand(data)
    data["demand"]["available"] = demand_available
    return data


def _market_provenance(market) -> dict[str, Any] | None:
    if market is None:
        return None
    return {
        "benchmark": "segment_avg",
        "area": market.area,
        "room_type": market.room_type,
        "avg_price": float(market.avg_price),
        "median_price": float(market.median_price),
        "percentile_25": float(market.percentile_25),
        "percentile_75": float(market.percentile_75),
        "min_price": float(market.min_price),
        "max_price": float(market.max_price),
        "sample_size": market.sample_size,
        "calculated_at": market.calculated_at.isoformat() if market.calculated_at else None,
    }


def public_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Project the staff-internal keys out of a computed result."""
    return {key: result[key] for key in _PUBLIC_KEYS}


def get_property_intelligence(
    room,
    *,
    include_internal: bool = False,
) -> dict[str, Any]:
    """Compute (or cache-read) the Property Intelligence result for ``room``.

    ``room`` may be a ``Room`` instance or an id (refetched once so the
    engine never depends on the caller's prefetch state). ``include_internal``
    returns provenance + engine metadata for staff callers only.
    """
    from rooms.models import Room

    if not isinstance(room, Room):
        room = (
            Room.objects.select_related("owner")
            .prefetch_related("images", "photo_moderations")
            .get(pk=room)
        )

    cfg = _config()
    signature = scoring.config_signature(
        cfg["weights"],
        quality_enabled=cfg["quality_enabled"],
        threshold_vars={"stale_days": cfg["stale_days"]},
    )
    key = f"property-intelligence:{room.pk}:{signature}"

    cached = safe_cache_get(key)
    if cached is not None:
        result = cached
        result["_engine"]["cache_hit"] = True
        return result if include_internal else public_payload(result)

    data = _collect(room, cfg["weights"], cfg["stale_days"])
    composed = scoring.compute_property_intelligence(data, cfg["weights"])
    result = {
        "room_id": room.pk,
        **composed,
        "computed_at": timezone.now().isoformat(),
        "data_freshness": data["freshness"],
        "provenance": data["provenance"],
        "_engine": {
            "version": SCORE_VERSION,
            "config_signature": signature,
            "weights": cfg["weights"],
            "cache_hit": False,
        },
    }
    if not cfg["enabled"]:
        result = {
            "room_id": room.pk,
            "score": None,
            "confidence": "none",
            "confidence_reasons": ["Property Intelligence is disabled."],
            "score_version": SCORE_VERSION,
            "computed_at": timezone.now().isoformat(),
            "breakdown": {},
            "strengths": [],
            "suggestions": [],
            "data_freshness": {},
            "disclaimer": DISCLAIMER,
            "provenance": {},
            "_engine": {
                "version": SCORE_VERSION,
                "config_signature": "disabled",
                "cache_hit": False,
            },
        }
        safe_cache_set(key, result, timeout=cfg["ttl"])
        return result if include_internal else public_payload(result)

    safe_cache_set(key, result, timeout=cfg["ttl"])
    result["_engine"]["cache_hit"] = False
    return result if include_internal else public_payload(result)


def invalidate_for_room(room_id: int) -> None:
    """Delete the cache key for ``room_id`` under the *current* config.

    Config changes mint a new key anyway; this covers the same-config
    invalidation events (price/image/verification changes).
    """
    from config.cache_utils import safe_cache_delete

    cfg = _config()
    signature = scoring.config_signature(
        cfg["weights"],
        quality_enabled=cfg["quality_enabled"],
        threshold_vars={"stale_days": cfg["stale_days"]},
    )
    safe_cache_delete(f"property-intelligence:{room_id}:{signature}")
