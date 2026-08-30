"""Property Intelligence scoring rules — pure, DB-free, deterministic.

Consumes a plain ``data`` dict built by :mod:`property_intelligence.engine`
from existing Rentora signals (listing quality, price insight, market stats,
fraud/trust, photos, demand). Every rule here is hand-verifiable: nothing is
trained, nothing is invented, and an unavailable signal is never punished or
rewarded — its weight is redistributed across the available components so the
composite stays a bounded 0-100.

Components (Phase 19.1 spec categories):
- listing_quality  (A) — the existing transparent quality engine, reused.
- price_value      (B) — "price competitiveness vs market", never a valuation.
- location         (C) — metro/commute value (walk distance to curated MRT).
- photo_trust      (D) — photo completeness + authenticity signals. Individual
                        suspicion signals reduce a component; they are never a
                        fraud verdict.
- trust            (E) — verification + fraud severity, safe public phrasing.
- demand           (F) — 30-day booking strength with small-sample guards.

Versioning: ``SCORE_VERSION`` is emitted with every payload and mixed into
the cache key so historical semantics never silently change.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SCORE_VERSION = "property_intelligence_v1"

COMPONENTS = (
    "listing_quality",
    "price_value",
    "location",
    "photo_trust",
    "trust",
    "demand",
)

# Documented fallback weights (sum = 100). Used whenever the configured
# weights are malformed — a mis-configuration must degrade, never 500.
DEFAULT_WEIGHTS = {
    "listing_quality": 25,
    "price_value": 20,
    "location": 15,
    "photo_trust": 15,
    "trust": 15,
    "demand": 10,
}

DISCLAIMER = (
    "This score is an informational property intelligence indicator. It is "
    "not a property valuation, fraud verdict, or guarantee of rental "
    "performance."
)

# Strength phrasing only ever cites real components.
_STRENGTH_LABELS = {
    "listing_quality": "Complete, market-ready listing.",
    "price_value": "Priced competitively vs the market.",
    "location": "Good metro / transit access.",
    "photo_trust": "High-quality, trustworthy photos.",
    "trust": "Strong verification and trust signals.",
    "demand": "Healthy recent demand.",
}

# Classification -> 0-100 competitiveness (see the phase design doc).
_PRICE_VALUE_SCALE = {
    "great_deal": 95,
    "good_price": 90,
    "fair_price": 75,
    "above_average": 45,
    "overpriced": 20,
}

# Photo-anomaly base deduction per detector, one article of "authenticity".
_ANOMALY_PENALTY = {
    "duplicate_image": 10,
    "manipulated_image": 10,
    "photo_geo_mismatch": 15,
}
_SEVERITY_FACTOR = {"low": 1, "medium": 2, "high": 3}
_MAX_ANOMALY_DEDUCTION = 40

# A listing photo-moderation record at/above this risk deducts trust points.
_MODERATION_RISK_THRESHOLD = 60
_MODERATION_PENALTY = 20

# Geo consistency gives photos a small positive authenticity signal.
_GEOCONSISTENT_BONUS = 8
_GEO_CONSISTENT_KM = 5.0  # matches fraud photo_geo mismatch threshold spirit

_STRENGTH_MIN = 75


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def resolve_weights(configured: dict[str, Any] | None) -> dict[str, float]:
    """Return a validated weight map, falling back to ``DEFAULT_WEIGHTS``.

    Rules: all six components present, numeric, non-negative, sum exactly 100.
    """
    if not isinstance(configured, dict) or not configured:
        return dict(DEFAULT_WEIGHTS)
    try:
        weights = {key: float(configured[key]) for key in COMPONENTS if key in configured}
    except (TypeError, ValueError):
        weights = {}
    if len(weights) != len(COMPONENTS):
        logger.warning("property_intelligence: incomplete weights; using defaults")
        return dict(DEFAULT_WEIGHTS)
    if any(v < 0 for v in weights.values()):
        logger.warning("property_intelligence: negative weight; using defaults")
        return dict(DEFAULT_WEIGHTS)
    if abs(sum(weights.values()) - 100.0) > 1e-6:
        logger.warning("property_intelligence: weights do not sum to 100; using defaults")
        return dict(DEFAULT_WEIGHTS)
    return weights


def config_signature(
    weights: dict[str, float],
    *,
    quality_enabled: bool = True,
    threshold_vars: dict[str, Any] | None = None,
) -> str:
    """Short hash of everything that changes the score semantics.

    Mixing this into the cache key gives configuration-driven invalidation by
    construction: any weight/level/threshold change produces a fresh key.
    """
    payload = {
        "version": SCORE_VERSION,
        "weights": {k: w for k, w in sorted(weights.items())},
        "quality_enabled": quality_enabled,
        "thresholds": sorted((threshold_vars or {}).items()),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Component scorers — each returns (score, availability, note)
# ---------------------------------------------------------------------------


def score_listing_quality(data: dict[str, Any]) -> tuple[float, bool, str]:
    quality = data.get("listing_quality") or {}
    if not quality.get("available", True):
        return 0.0, False, "Listing quality engine is disabled."
    raw = quality.get("score")
    if raw is None:
        return 0.0, False, "Listing quality is unavailable."
    return float(min(100.0, max(0.0, raw))), True, ""


def score_price_value(data: dict[str, Any]) -> tuple[float, bool, str]:
    price = data.get("price")
    if not price or not price.get("available"):
        return 0.0, False, "No reliable price benchmark for this segment yet."
    classification = price.get("classification", "fair_price")
    return float(_PRICE_VALUE_SCALE.get(classification, 75)), True, price.get("message", "")


def score_location(data: dict[str, Any]) -> tuple[float, bool, str]:
    location = data.get("location")
    if not location or not location.get("available"):
        return 0.0, False, "Commute data is unavailable for this listing."
    metro = float(location.get("metro_score") or 0)
    if metro <= 0:
        return 0.0, True, "No metro station within walking distance."
    return float(_clamp(metro)), True, ""


def score_photo_trust(data: dict[str, Any]) -> tuple[float, bool, str]:
    photos = data.get("photos")
    if not photos or not photos.get("available", True):
        return 0.0, False, "Photo signals are unavailable."
    count = int(photos.get("count") or 0)
    if count == 0:
        return 0.0, True, "No photos — add photos of the room."
    if count >= 4:
        base = 100.0
    elif count >= 2:
        base = 75.0
    else:
        base = 50.0
    if not photos.get("has_primary") and count > 0:
        base = min(base, 60.0)

    deduction = 0.0
    for detector, severity in photos.get("anomalies") or []:
        penalty = _ANOMALY_PENALTY.get(detector, 0)
        deduction += penalty * _SEVERITY_FACTOR.get(severity, 1)
    if photos.get("moderation_risk", 0) >= _MODERATION_RISK_THRESHOLD:
        deduction += _MODERATION_PENALTY
    note = ""
    if deduction > 0:
        note = (
            f"Photo authenticity signals reduced the trust component by {round(deduction)} points."
        )
    bonus = _GEOCONSISTENT_BONUS if photos.get("gps_consistent") else 0
    score = _clamp(base - min(deduction, _MAX_ANOMALY_DEDUCTION) + bonus)
    return float(score), True, note


def score_trust(data: dict[str, Any]) -> tuple[float, bool, str]:
    trust = data.get("trust")
    if not trust or not trust.get("available", True):
        return 0.0, False, "Trust signals are unavailable."
    score = 55.0
    if trust.get("verified"):
        score += 25
    else:
        score -= 15
    if trust.get("nid_verified"):
        score += 10
    if trust.get("tenant_verified"):
        score += 5
    fraud = trust.get("fraud")
    if fraud and fraud.get("exists"):
        severity = fraud.get("severity", "clean")
        score += {"clean": 5, "low": -10, "medium": -25, "high": -40}.get(severity, 0)
    note = ""
    if not trust.get("verified"):
        note = "Verification information is incomplete."
    return float(_clamp(score)), True, note


def score_demand(data: dict[str, Any]) -> tuple[float, bool, str]:
    demand = data.get("demand")
    if not demand:
        return 0.0, False, "Demand signals are unavailable."
    own = demand.get("own") or {}
    views = int(own.get("views") or 0)
    saves = int(own.get("saves") or 0)
    requests = int(own.get("requests") or 0)
    own_signals = views + saves + requests
    own_weighted = views + saves * 3 + requests * 6
    own_score = float(_clamp((own_weighted / 20.0) * 100))

    area = demand.get("area") or {}
    area_score = area.get("score")
    area_total = int(area.get("total_signals") or 0)

    # Small-sample guard: with no own pull and a near-empty area, don't
    # present a confident number — mark the signal unavailable.
    if own_signals == 0 and area_total < 3:
        return 0.0, False, "Not enough activity data yet to estimate demand."
    if area_score is None:
        if own_signals == 0:
            return 0.0, False, "Not enough activity data yet to estimate demand."
        return (
            own_score,
            True,
            "Limited recent demand data — based on this listing's own signals.",
        )
    if own_signals < 2:
        return (
            float(_clamp(area_score)),
            True,
            ("Listing has limited recent demand data — using the area trend."),
        )
    blend = 0.4 * own_score + 0.6 * float(_clamp(area_score))
    return float(_clamp(blend)), True, ""


# ---------------------------------------------------------------------------
# Composition, confidence, suggestions, strengths
# ---------------------------------------------------------------------------


def _available_components(
    data: dict[str, Any], scorer_map: dict[str, Any]
) -> dict[str, tuple[float, str]]:
    """Map component -> (score, note) for the components with live data."""
    out: dict[str, tuple[float, str]] = {}
    for name, scorer in scorer_map.items():
        score, available, note = scorer(data)
        if available:
            out[name] = (score, note)
    return out


def confidence_level(data: dict[str, Any], breakdown: dict[str, Any]) -> tuple[str, list[str]]:
    """Deterministic confidence from availability, sample size and freshness."""
    available = [k for k, meta in breakdown.items() if meta.get("availability") == "available"]
    demand_available = "demand" in available
    points = 3 if len(available) >= 5 else 2 if len(available) >= 3 else 1
    reasons: list[str] = []

    if len(available) < len(COMPONENTS):
        missing = len(COMPONENTS) - len(available)
        reasons.append(f"{missing} signal {'group' if missing == 1 else 'groups'} unavailable.")
    if not demand_available:
        points -= 1
        reasons.append("limited booking history")
    price = data.get("price")
    if price and price.get("available") and int(price.get("sample_size") or 0) < 5:
        points -= 1
        reasons.append("small price benchmark sample")
    stale_days = int(data.get("stale_days") or 0)
    if stale_days >= int(data.get("stale_threshold_days") or 90):
        points -= 1
        reasons.append("stale listing data")
    if not reasons and len(available) == len(COMPONENTS):
        reasons.append("strong listing data")
        if price and price.get("available"):
            reasons.append("sufficient price comparables")

    level = "high" if points >= 3 else "medium" if points == 2 else "low"
    return level, reasons


def _component_suggestions(breakdown: dict[str, Any], data: dict[str, Any]) -> list[str]:
    available = {k for k, meta in breakdown.items() if meta.get("availability") == "available"}
    out: list[str] = []
    price = data.get("price")
    photos = data.get("photos") or {}
    trust = data.get("trust") or {}

    if price and price.get("available") and price.get("classification") == "overpriced":
        out.append("Price is above comparable listings in this area.")
    if photos and photos.get("count") and not photos.get("has_primary"):
        out.append("Set a primary photo so the listing looks complete.")
    if photos and int(photos.get("count") or 0) < 4:
        out.append("Add more high-quality photos.")
    if trust and not trust.get("verified"):
        out.append("Verification information is incomplete — complete owner verification.")
    if "demand" not in available:
        out.append("Listing has limited recent demand data.")
    location = data.get("location")
    if location and not location.get("available"):
        out.append("Commute data is unavailable for this listing.")
    if int(data.get("stale_days") or 0) >= int(data.get("stale_threshold_days") or 90):
        out.append("Listing data is stale — update the listing.")
    return out


def _strengths(breakdown: dict[str, Any]) -> list[str]:
    out = []
    for name in COMPONENTS:
        meta = breakdown.get(name) or {}
        if (
            meta.get("availability") == "available"
            and float(meta.get("score") or 0) >= _STRENGTH_MIN
        ):
            out.append(_STRENGTH_LABELS[name])
    return out


def compute_property_intelligence(
    data: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compose the component scores into one transparent 0-100 result.

    ``data`` must contain the per-component payloads (see engine). Returns a
    dict with ``score`` (int or None), ``confidence``, ``breakdown``,
    ``strengths``, ``suggestions`` and ``disclaimer``.
    """
    weights = resolve_weights(weights)
    scorer_map = {
        "listing_quality": score_listing_quality,
        "price_value": score_price_value,
        "location": score_location,
        "photo_trust": score_photo_trust,
        "trust": score_trust,
        "demand": score_demand,
    }
    available = _available_components(data, scorer_map)
    score_meta = {name: (0.0, "") for name in COMPONENTS}
    for name in available:
        score_meta[name] = available[name]

    breakdown: dict[str, dict[str, Any]] = {}
    for name in COMPONENTS:
        value, note = score_meta[name]
        available_now = name in available
        breakdown[name] = {
            "score": None if not available_now else round(value),
            "weight": weights[name],
            "effective_weight": round(weights[name], 2),
            "contribution": None,
            "availability": "available" if available_now else "unavailable",
        }
        if note and available_now:
            breakdown[name]["note"] = note

    # Redistribute unavailable weight over the available components so the
    # composite stays 0-100 and honest (missing data never inflates it).
    available_names = [n for n in COMPONENTS if n in available]
    total_weight = sum(weights[n] for n in available_names)
    if available_names and total_weight > 0:
        for name in available_names:
            effective = weights[name] * (100.0 / total_weight)
            breakdown[name]["effective_weight"] = round(effective, 2)
            breakdown[name]["contribution"] = round(effective * score_meta[name][0] / 100.0, 2)
        total = sum(breakdown[n]["contribution"] for n in available_names)
        score = round(total)
    else:
        score = None

    confidence, reasons = confidence_level(data, breakdown)
    if score is None:
        confidence = "none"

    return {
        "score": score,
        "confidence": confidence,
        "confidence_reasons": reasons,
        "score_version": SCORE_VERSION,
        "breakdown": breakdown,
        "strengths": _strengths(breakdown),
        "suggestions": (
            _component_suggestions(breakdown, data) + list(data.get("quality_suggestions") or [])
        )[:5],
        "disclaimer": DISCLAIMER,
    }
