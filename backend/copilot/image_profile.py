"""Image profile for the Copilot (Tier 5 — image understanding).

When a user asks "what does this room look like?", the Copilot answers from
the listing's *actual* photos using deterministic, self-hosted analysis —
no external vision API, no invented captions:

- **Brightness** — mean luminance (dark / normal / bright).
- **Colourfulness** — how saturated the palette is (muted / colourful).
- **Dominant tones** — the top 2 quantized hues, labelled in plain English
  (warm beige, cool grey, …) so the answer is human, not hex codes.

Honesty contract: this is *statistical* description of the pixels, not
semantic recognition — we can say the primary photo is bright and warm, we
cannot say "there is a double bed". The answer text says exactly that.
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageStat

_NONE: dict[str, Any] = {
    "available": False,
    "brightness": None,
    "colourfulness": None,
    "tones": [],
    "count": 0,
}


def _lab_tone(rgb: tuple[int, int, int]) -> str:
    """Coarse human label for a pixel's dominant tone."""
    r, g, b = rgb
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / 255.0
    if sat < 0.12:
        if mx < 80:
            return "dark grey"
        return "neutral white/grey"
    hue = None
    if mx == r:
        hue = (60 * ((g - b) / (mx - mn))) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    if hue < 0:
        hue += 360
    if hue < 15 or hue >= 345:
        return "warm red"
    if hue < 45:
        return "warm orange/amber"
    if hue < 70:
        return "warm yellow"
    if hue < 160:
        return "cool green"
    if hue < 200:
        return "cool teal"
    if hue < 260:
        return "cool blue"
    return "cool purple/magenta"


def image_profile(path: str) -> dict[str, Any]:
    """Profile one image file. Never raises for a missing/bad file — the
    caller gets ``available: False`` and treats it as no-photo-info."""
    try:
        img = Image.open(path)
        img.load()
        img = img.convert("RGB")
    except Exception:
        return dict(_NONE)

    # Downscale for speed — we only need global statistics.
    img.thumbnail((240, 240))
    stat = ImageStat.Stat(img)
    mean = tuple(int(v) for v in stat.mean)
    brightness = (sum(mean) / 3) / 255.0

    if brightness < 0.3:
        brightness_label = "dark"
    elif brightness < 0.62:
        brightness_label = "normal"
    else:
        brightness_label = "bright"

    # Colourfulness: mean per-pixel saturation distance from grey.
    r, g, b = img.split()

    rg = [abs(a - bb) for a, bb in zip(r.getdata(), g.getdata(), strict=True)]
    yb = [
        abs(2 * a - bb - cc)
        for a, bb, cc in zip(r.getdata(), g.getdata(), b.getdata(), strict=True)
    ]
    colourfulness = (
        math.sqrt(sum(x * x for x in rg) / len(rg) + sum(x * x for x in yb) / len(yb)) / 180.0
    )

    colour_label = "muted" if colourfulness < 0.12 else "colourful"

    # Dominant tones: quantize to 64 levels, count buckets.
    small = img.resize((64, 64))
    counts: dict[tuple[int, int, int], int] = {}
    for px in small.getdata():
        bucket = (px[0] // 64 * 64 + 32, px[1] // 64 * 64 + 32, px[2] // 64 * 64 + 32)
        counts[bucket] = counts.get(bucket, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:2]
    tones = [_lab_tone(bucket) for bucket, _ in top]

    return {
        "available": True,
        "brightness": brightness_label,
        "colourfulness": colour_label,
        "tones": tones,
        "count": 1,
    }


def listing_image_profile(room) -> dict[str, Any]:
    """Aggregate profile across a listing's photos: the primary image's
    stats plus the total photo count. Returns ``available: False`` when the
    listing has no readable photos (or no photos at all)."""
    images = list(room.images.all()[:5])
    if not images:
        return dict(_NONE)

    primary = next((i for i in images if i.is_primary), images[0])
    try:
        profile = image_profile(primary.image.path)
    except Exception:
        profile = dict(_NONE)

    profile["count"] = len(images)
    return profile
