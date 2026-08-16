"""Photo forensics (Tier 2).

Pure-Pillow heuristics that extend the existing duplicate-image fraud layer
with *manipulation* signals:

- **ELA (Error Level Analysis)** — re-encode the file at a known JPEG
  quality and measure the pixel difference. Real camera photos lose detail
  roughly uniformly; pasted/cloned regions carry a different error level,
  so tampering shows up as a mean spike or a hot localized tail (p99).
- **Watermark / overlay band** — a caption or watermark bar is typically a
  large, unusually uniform strip along an edge; we compare corner-band
  variance against body variance.
- **Editor software** — EXIF ``Software`` naming a heavy editor (Photoshop,
  Canva, ...) is a weak, non-blocking signal (legit edited photos exist).
- **Tiny / low-quality** — a listing photo that is smaller than a real
  camera/phone output is either a reused thumbnail or unrelated stock.

Honesty contract: every signal is a *suspicion to review*, never proof.
The engine reports keys + scores; admins see the evidence and decide.
Detection is bounded (first N images, per-image timeouts are not needed —
files are already size-limited at upload).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageChops, ImageStat

# ---- tuning -----------------------------------------------------------------
ELA_QUALITY = 90  # re-encode quality for the ELA pass
ELA_MEAN_TAMPER = 14.0  # mean diff above this → likely tampering
ELA_P99_TAMPER = 60.0  # localized (99th pct) diff above this → tamper region
MIN_DIMENSION = 400  # px — smaller is not a real listing photo
MIN_FILE_BYTES = 25 * 1024  # 25 KB
WATERMARK_BAND_FRAC = 0.10  # corner band = 10% of the axis
WATERMARK_VAR_RATIO = 3.0  # band stddev < body stddev / ratio → overlay
BODY_VAR_MIN = 18.0  # body must have texture for the overlay test to mean anything

_EDITOR_MARKERS = (
    "photoshop",
    "adobe",
    "canva",
    "gimp",
    "pixlr",
    "paint.net",
    "affinity",
    "lightroom",
    "stablediffusion",
    "midjourney",
    "firefly",
)


@dataclass
class ForensicSignal:
    """One forensics finding — key, human label, severity, and a 0..1
    confidence-style score so admins can sort the queue."""

    key: str
    label: str
    severity: str  # "low" | "medium"
    score: float

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "severity": self.severity,
            "score": round(self.score, 2),
        }


@dataclass
class ForensicsResult:
    """Everything learned about one image file."""

    filename: str
    signals: list[ForensicSignal] = field(default_factory=list)
    ela_mean: float = 0.0
    ela_p99: float = 0.0
    parsed: bool = False

    @property
    def worst_severity(self) -> str | None:
        order = ["medium", "low"]
        for sev in order:
            if any(s.severity == sev for s in self.signals):
                return sev
        return None


def _ela_stats(img: Image.Image) -> tuple[float, float]:
    """Mean + 99th-percentile pixel diff after a JPEG re-encode pass."""
    rgb = img.convert("RGB")
    buf = BytesIO()
    rgb.save(buf, "JPEG", quality=ELA_QUALITY)
    buf.seek(0)
    reencoded = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(rgb, reencoded)

    # Sum the RGB histogram into one per-pixel error histogram.
    hist = diff.histogram()  # 256 entries per channel
    n_channels = 3
    total_pixels = sum(hist) // n_channels
    if total_pixels == 0:
        return 0.0, 0.0
    mean = sum(i * (hist[i] + hist[i + 256] + hist[i + 512]) for i in range(256)) / (
        total_pixels * n_channels
    )
    # 99th percentile of the per-pixel max error — a hot region.
    threshold = 0.99 * total_pixels
    cumulative = 0
    p99 = 0.0
    for i in range(256):
        cumulative += hist[i] + hist[i + 256] + hist[i + 512]
        if cumulative >= threshold * n_channels:
            p99 = float(i)
            break
    return mean, p99


_ELA_GRID = 8  # 8x8 blocks for the local-ELA consistency check
_ELA_BLOCK_INCONSISTENCY = 2.5  # max/min block error ratio above this → paste


def _ela_block_consistency(img: Image.Image) -> float:
    """Ratio of the highest to the lowest *block-level* ELA error.

    A genuinely captured photo has roughly uniform error across blocks;
    a pasted region from another compression generation carries a
    measurably different error level, so this ratio spikes. Returns 1.0
    (no inconsistency) when the image is too small to grid or fully flat.
    """
    rgb = img.convert("RGB")
    buf = BytesIO()
    rgb.save(buf, "JPEG", quality=ELA_QUALITY)
    buf.seek(0)
    reencoded = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(rgb, reencoded).convert("L")

    w, h = diff.size
    bw, bh = max(1, w // _ELA_GRID), max(1, h // _ELA_GRID)
    block_means: list[float] = []
    for gy in range(_ELA_GRID):
        for gx in range(_ELA_GRID):
            box = (gx * bw, gy * bh, min(w, (gx + 1) * bw), min(h, (gy + 1) * bh))
            stat = ImageStat.Stat(diff.crop(box))
            block_means.append(float(stat.mean[0]))

    nonzero = [b for b in block_means if b > 0.05]
    if len(nonzero) < _ELA_GRID:  # too flat to judge
        return 1.0
    low = min(nonzero)
    high = max(nonzero)
    return (high / low) if low > 0 else 1.0


def _corner_band_variance(img: Image.Image) -> float:
    """Stddev of the bottom band — caption/watermark bars live there."""
    w, h = img.size
    band_h = max(1, int(h * WATERMARK_BAND_FRAC))
    band = img.convert("L").crop((0, h - band_h, w, h))
    stat = ImageStat.Stat(band)
    return float(stat.stddev[0])


def _body_variance(img: Image.Image) -> float:
    """Stddev of the image minus the bottom band (the textured reference)."""
    w, h = img.size
    band_h = max(1, int(h * WATERMARK_BAND_FRAC))
    body = img.convert("L").crop((0, 0, w, h - band_h))
    stat = ImageStat.Stat(body)
    return float(stat.stddev[0])


def analyze_image(path: str) -> ForensicsResult:
    """Run the forensics pipeline over one image file. Never raises for a
    bad/missing file — it returns an unparsed result so callers can treat
    it as 'no signals' safely."""
    result = ForensicsResult(filename=os.path.basename(path))
    try:
        img = Image.open(path)
        img.load()
    except Exception:
        return result

    result.parsed = True
    width, height = img.size

    ela_mean, ela_p99 = _ela_stats(img)
    block_ratio = _ela_block_consistency(img)
    result.ela_mean = round(ela_mean, 2)
    result.ela_p99 = round(ela_p99, 2)

    if (
        ela_mean > ELA_MEAN_TAMPER
        or ela_p99 > ELA_P99_TAMPER
        or block_ratio > _ELA_BLOCK_INCONSISTENCY
    ):
        result.signals.append(
            ForensicSignal(
                key="ela_tamper",
                label="Possible image manipulation (inconsistent error levels)",
                severity="medium",
                score=min(
                    1.0,
                    0.4 + max(ela_mean / 60.0, ela_p99 / 200.0, (block_ratio - 1.0) / 4.0),
                ),
            )
        )

    try:
        exif = img.getexif()
        software = str(exif.get(305, "") or exif.get("Software", "")).lower()
        if software and any(marker in software for marker in _EDITOR_MARKERS):
            result.signals.append(
                ForensicSignal(
                    key="editor_software",
                    label="Image edited with desktop software",
                    severity="low",
                    score=0.55,
                )
            )
    except Exception:
        pass

    if min(width, height) < MIN_DIMENSION:
        result.signals.append(
            ForensicSignal(
                key="tiny_image",
                label=f"Image is only {width}x{height}px - too small for a real listing photo",
                severity="low",
                score=0.6,
            )
        )

    file_size = os.path.getsize(path) if os.path.exists(path) else 0
    if file_size < MIN_FILE_BYTES:
        result.signals.append(
            ForensicSignal(
                key="low_quality_file",
                label="Very small file — possibly a recompressed thumbnail",
                severity="low",
                score=0.55,
            )
        )

    band_var = _corner_band_variance(img)
    body_var = _body_variance(img)
    if body_var > BODY_VAR_MIN and band_var * WATERMARK_VAR_RATIO < body_var:
        result.signals.append(
            ForensicSignal(
                key="watermark_overlay",
                label="Uniform band along the bottom — possible watermark/caption",
                severity="low",
                score=min(1.0, 0.35 + body_var / 100.0),
            )
        )

    return result
