"""Vision & content AI (Phase 14 — AI v3).

Three deterministic, self-hosted capabilities built on the listing's actual
photos (Pillow only — no external model is required for the core):

1. **Photo → description** — a caption and observations derived from real
   pixel statistics (lighting, tone, décor richness, composition) that feed
   the listing-draft generator.
2. **Auto amenity tagging** — a pluggable vision gateway (``http`` provider)
   may return object-level amenity tags; the built-in ``heuristic`` provider
   returns conservative *observations* and never invents furniture it cannot
   see. Suggested tags are always reviewed before applying.
3. **AI image search** — upload a photo and find listings whose photos look
   alike: 64-bit pHash (Hamming distance) + colour-histogram intersection +
   brightness delta combined into a transparent 0-100 match score with
   human-readable reasons.

Honesty contract (same as the Copilot image profile): this is statistical
description of pixels, not semantic recognition. We can say a photo is
bright, warm-toned and wide-angle; we cannot say "there is a double bed".
Every response carries a ``note`` saying exactly that.
"""

from __future__ import annotations

import io
import logging
import math
from typing import Any

from django.conf import settings

from .image_search import average_hash, hamming_distance

logger = logging.getLogger(__name__)

_PALETTE_N = 3  # dominant colours returned per photo
_HIST_LEVELS = 4  # per channel -> 4^3 = 64 histogram buckets
_PROFILE_LIMIT = 5  # photos profiled per listing
_SEARCH_WEIGHTS = {"phash": 0.5, "hist": 0.25, "brightness": 0.25}
_SEARCH_MIN_SCORE = 35  # below this, a room is not a visual match (of 100)
_GATEWAY_TIMEOUT_SECONDS = 10

_NONE: dict[str, Any] = {
    "available": False,
    "reason": "no readable photos",
}


def _color_name(rgb: tuple[int, int, int]) -> str:
    """Plain-English name for an RGB colour (deterministic)."""
    r, g, b = rgb
    mx, mn = max(r, g, b), min(r, g, b)
    light = mx / 255.0
    sat = (mx - mn) / 255.0 if mx else 0.0

    if sat < 0.1:
        if light < 0.12:
            return "charcoal"
        if light < 0.35:
            return "dark grey"
        if light < 0.75:
            return "light grey"
        if light < 0.95:
            return "off-white"
        return "white"

    hue = 0.0
    if mx == r:
        hue = (60 * ((g - b) / (mx - mn))) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    if hue < 0:
        hue += 360

    warm_brown = light < 0.55 and hue < 45
    if hue < 15 or hue >= 345:
        return "deep red" if light < 0.4 else "warm red"
    if hue < 45:
        if warm_brown or sat < 0.45:
            return "wood brown" if light < 0.5 else "warm beige"
        return "warm orange"
    if hue < 70:
        return "amber yellow" if sat > 0.5 else "soft yellow"
    if hue < 160:
        return "soft green"
    if hue < 200:
        return "teal"
    if hue < 260:
        return "cool blue"
    return "purple" if sat > 0.35 else "mauve"


def _brightness_label(value: float) -> str:
    if value < 0.3:
        return "dark"
    if value < 0.62:
        return "normal"
    return "bright"


def _colourfulness_label(value: float) -> str:
    return "colourful" if value >= 0.14 else "muted"


def _histogram(img, levels: int = _HIST_LEVELS) -> list[float]:
    """Normalised per-channel-quantised colour histogram (deterministic)."""
    small = img.resize((64, 64))
    bins = levels * levels * levels
    counts = [0] * bins
    for px in small.getdata():
        idx = (px[0] * levels // 256) * levels * levels
        idx += (px[1] * levels // 256) * levels
        idx += px[2] * levels // 256
        counts[idx] += 1
    total = sum(counts) or 1
    return [c / total for c in counts]


def _hist_intersection(a: list[float], b: list[float]) -> float:
    return sum(min(x, y) for x, y in zip(a, b, strict=True))


def _palette(img, top_n: int = _PALETTE_N) -> list[dict[str, Any]]:
    """Top ``top_n`` dominant colours: ``{hex, name, share}``."""
    try:
        small = img.resize((128, 128))
        quantized = small.convert("RGB").quantize(colors=16)
        counts: dict[tuple[int, int, int], int] = {}
        for _idx, px in enumerate(quantized.getdata()):
            rgb = quantized.getpalette()[px * 3 : px * 3 + 3]
            counts[tuple(rgb)] = counts.get(tuple(rgb), 0) + 1
        total = sum(counts.values()) or 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return [
            {
                "hex": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
                "name": _color_name(rgb),
                "share": round(count / total, 3),
            }
            for rgb, count in top
        ]
    except Exception as exc:
        logger.warning("palette failed: %s", exc)
        return []


def fingerprint_image(source) -> dict[str, Any] | None:
    """One image's visual fingerprint.

    ``source`` is either a filesystem path (str/Path) or raw bytes. Returns
    ``None`` for unreadable/non-image input — never raises.
    """
    try:
        from PIL import Image, ImageStat

        if isinstance(source, (bytes, bytearray)):
            img = Image.open(io.BytesIO(bytes(source)))
        else:
            img = Image.open(source)
        img.load()
        img = img.convert("RGB")
    except Exception as exc:
        logger.warning("fingerprint: unreadable image: %s", exc)
        return None

    width, height = img.size
    if width < 4 or height < 4:
        return None

    thumb = img.copy()
    thumb.thumbnail((240, 240))
    stat = ImageStat.Stat(thumb)
    mean = tuple(int(v) for v in stat.mean)
    brightness = (sum(mean) / 3) / 255.0

    r, g, b = thumb.split()
    rg = [abs(a - bb) for a, bb in zip(r.getdata(), g.getdata(), strict=True)]
    yb = [
        abs(2 * a - bb - cc)
        for a, bb, cc in zip(r.getdata(), g.getdata(), b.getdata(), strict=True)
    ]
    colourfulness = (
        math.sqrt(sum(x * x for x in rg) / len(rg) + sum(x * x for x in yb) / len(yb)) / 180.0
    )

    phash = average_hash(img)

    return {
        "phash": phash,
        "brightness": round(brightness, 3),
        "brightness_label": _brightness_label(brightness),
        "colourfulness": round(colourfulness, 3),
        "colourfulness_label": _colourfulness_label(colourfulness),
        "palette": _palette(img),
        "histogram": _histogram(img),
        "aspect": round(width / height, 2) if height else None,
        "width": width,
        "height": height,
    }


def listing_photo_profiles(room, limit: int = _PROFILE_LIMIT) -> list[dict[str, Any]]:
    """Fingerprints for a listing's photos, best-effort."""
    profiles: list[dict[str, Any]] = []
    for image in room.images.all()[:limit]:
        try:
            path = image.image.path
        except Exception:
            continue
        profile = fingerprint_image(path)
        if profile:
            profiles.append(profile)
    return profiles


def observations_from_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic, conservative observations from photo statistics."""
    if not profiles:
        return []
    observations: list[dict[str, Any]] = []

    brightness = sum(p["brightness"] for p in profiles) / len(profiles)
    if brightness < 0.3:
        label, confidence = "Cozy, low-lit interior", 0.9
    elif brightness < 0.62:
        label, confidence = "Balanced natural lighting", 0.9
    else:
        label, confidence = "Bright, well-lit interior", 0.9
    observations.append({"kind": "lighting", "label": label, "confidence": confidence})

    names = [c["name"] for p in profiles for c in p["palette"]]
    warm = any(n in names for n in ("wood brown", "warm beige", "warm orange", "amber yellow"))
    cool = any(n in names for n in ("cool blue", "teal", "soft green", "mauve", "purple"))
    if warm and not cool:
        label = "Warm wood and beige tones dominate"
    elif cool and not warm:
        label = "Cool-toned palette"
    else:
        label = "Neutral palette"
    observations.append({"kind": "tone", "label": label, "confidence": 0.85})

    colourfulness = sum(p["colourfulness"] for p in profiles) / len(profiles)
    if colourfulness >= 0.14:
        label, confidence = "Colourful décor accents", 0.8
    else:
        label, confidence = "Minimal, muted décor", 0.8
    observations.append({"kind": "decor", "label": label, "confidence": confidence})

    if any((p["aspect"] or 0) >= 1.4 for p in profiles):
        label, confidence = "Wide-angle room shots", 0.75
    elif all((p["aspect"] or 1) < 0.95 for p in profiles):
        label, confidence = "Vertical room shots", 0.75
    else:
        label, confidence = "Mixed photo framing", 0.75
    observations.append({"kind": "composition", "label": label, "confidence": confidence})

    return observations


def heuristic_caption(profiles: list[dict[str, Any]], observations: list[dict[str, Any]]) -> str:
    """A deterministic one-line caption built from real photo statistics."""
    if not profiles:
        return ""
    by_kind = {obs["kind"]: obs["label"] for obs in observations}
    parts = [
        by_kind.get("lighting", ""),
        by_kind.get("tone", ""),
        by_kind.get("decor", ""),
    ]
    caption = "Photos show a " + ", ".join(p for p in parts if p) + " interior."
    if len(profiles) == 1:
        caption += " Single photo on file."
    else:
        caption += f" {len(profiles)} photos on file."
    return caption


def _gateway_analyze(room, request=None) -> dict[str, Any] | None:
    """Ask the configured vision gateway for a caption + amenity tags.

    Strict parsing: any deviation (bad JSON, wrong types, oversized fields,
    network error, timeout) returns ``None`` and the caller falls back to the
    heuristic provider — a gateway outage never breaks listing drafts.
    """
    url = settings.VISION_GATEWAY_URL
    api_key = settings.VISION_GATEWAY_API_KEY
    if not url:
        return None

    images = list(room.images.all()[:3])
    if not images:
        return None
    image_urls = []
    for image in images:
        if request is None:
            continue
        try:
            image_urls.append(request.build_absolute_uri(settings.MEDIA_URL + image.image.name))
        except Exception:
            continue
    if not image_urls:
        return None

    import requests

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload: dict[str, Any] = {"images": image_urls}
    if settings.VISION_GATEWAY_MODEL:
        payload["model"] = settings.VISION_GATEWAY_MODEL
    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=_GATEWAY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("vision gateway failed (falling back to heuristic): %s", exc)
        return None

    caption = str(data.get("caption", ""))[:400]
    amenities = [
        str(a).strip().lower()[:40]
        for a in data.get("amenities", [])[:8]
        if isinstance(a, str) and a.strip()
    ]
    return {"caption": caption or None, "amenities": amenities}


def analyze_listing(room, request=None) -> dict[str, Any]:
    """Full vision analysis for one listing. Never raises."""
    profiles = listing_photo_profiles(room)
    if not profiles:
        return dict(_NONE)

    observations = observations_from_profiles(profiles)
    caption = heuristic_caption(profiles, observations)
    suggested_amenities: list[str] = []
    provider = "heuristic"

    if settings.VISION_PROVIDER == "http":
        gateway = _gateway_analyze(room, request)
        if gateway:
            provider = "http"
            if gateway.get("caption"):
                caption = gateway["caption"]
            suggested_amenities = gateway.get("amenities") or []

    palette: list[dict[str, Any]] = []
    for profile in profiles:
        for colour in profile["palette"]:
            palette.append(colour)

    return {
        "available": True,
        "provider": provider,
        "caption": caption,
        "observations": observations,
        "suggested_amenities": suggested_amenities,
        "palette": palette,
        "photo_profiles": [{k: v for k, v in p.items() if k != "histogram"} for p in profiles],
        "photo_count": len(profiles),
        "note": (
            "Photo intelligence is statistical (lighting, tones, décor, framing) — "
            "it cannot name specific furniture. Object-level amenity tags come "
            "from a configured vision gateway; suggested tags are for review only."
        ),
    }


def _room_primary_profile(room) -> dict[str, Any] | None:
    primary = room.images.filter(is_primary=True).first() or room.images.first()
    if primary is None:
        return None
    try:
        path = primary.image.path
    except Exception:
        return None
    return fingerprint_image(path)


def image_search(query_bytes: bytes, top_k: int | None = None) -> list[dict[str, Any]]:
    """Rank listings by how much their primary photo resembles the query.

    Score (0-100) = 50% pHash similarity + 25% colour-histogram intersection
    + 25% brightness closeness. Returns matches above ``_SEARCH_MIN_SCORE``,
    nearest first, each with transparent ``reasons``.
    """
    query_fp = fingerprint_image(query_bytes)
    if query_fp is None or not query_fp.get("phash"):
        return []
    top_k = top_k or settings.VISION_SEARCH_TOP_K

    from .models import Room

    scored: list[tuple[float, dict[str, Any]]] = []
    for room in Room.objects.all().prefetch_related("images"):
        profile = _room_primary_profile(room)
        if profile is None or not profile.get("phash"):
            continue

        phash_sim = 1 - min(hamming_distance(query_fp["phash"], profile["phash"]), 32) / 32
        hist_sim = _hist_intersection(query_fp["histogram"], profile["histogram"])
        brightness_sim = 1 - abs(query_fp["brightness"] - profile["brightness"])
        score = (
            _SEARCH_WEIGHTS["phash"] * phash_sim
            + _SEARCH_WEIGHTS["hist"] * hist_sim
            + _SEARCH_WEIGHTS["brightness"] * brightness_sim
        )
        score = round(score * 100)
        if score < _SEARCH_MIN_SCORE:
            continue

        reasons: list[str] = []
        if phash_sim >= 0.6:
            reasons.append("similar photo composition")
        if hist_sim >= 0.55:
            reasons.append("similar colour palette")
        if brightness_sim >= 0.85:
            reasons.append("similar lighting")
        if not reasons:
            reasons.append("overall visual similarity")

        scored.append((score, {"room_id": room.pk, "match_score": score, "reasons": reasons}))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _score, item in scored[:top_k]]
