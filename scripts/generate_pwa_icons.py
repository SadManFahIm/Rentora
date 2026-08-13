"""Generate Rentora's PWA icon set.

Brand design: orange rounded-square background (Tailwind orange-500 -> orange-700
vertical gradient) with a white house silhouette and an orange door.

Outputs (relative to the repo root, unless --out is given):
  frontend/public/icons/icon-192.png      192x192  any
  frontend/public/icons/icon-512.png      512x512  any
  frontend/public/icons/maskable-512.png  512x512  maskable (full-bleed, safe zone)
  frontend/public/icons/apple-touch-180.png 180x180 apple-touch
  frontend/public/icons/favicon-32.png    32x32
  frontend/public/icons/favicon-48.png    48x48
  frontend/public/icons/favicon-96.png    96x96
  frontend/public/icons/favicon-144.png   144x144

Usage:
  python scripts/generate_pwa_icons.py

Requires Pillow (already a backend dependency for pHash).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

# Tailwind orange ramp used by the design tokens (--color-brand = orange-600).
ORANGE_TOP = (249, 115, 22)  # orange-500
ORANGE_BOTTOM = (194, 65, 12)  # orange-700
DOOR = (234, 88, 12)  # orange-600
WHITE = (255, 255, 255)


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        color = lerp(top, bottom, y / (size - 1))
        for x in range(size):
            px[x, y] = color
    return img


def draw_house(draw: ImageDraw.ImageDraw, size: int, scale: float, door_color: tuple[int, int, int]) -> None:
    """Draw the white house centered in a `size` canvas, scaled by `scale` (0..1)."""
    cx = size / 2
    base_w = 0.44 * size * scale
    base_h = 0.30 * size * scale
    roof_h = 0.16 * size * scale

    left = cx - base_w / 2
    right = cx + base_w / 2
    roof_top_y = (size - base_h - roof_h) / 2
    body_top_y = roof_top_y + roof_h
    body_bottom_y = body_top_y + base_h

    # Roof: triangle peeking slightly wider than the body.
    draw.polygon(
        [
            (left - base_w * 0.06, body_top_y),
            (cx, roof_top_y),
            (right + base_w * 0.06, body_top_y),
        ],
        fill=WHITE,
    )
    # Body.
    draw.rectangle([left, body_top_y, right, body_bottom_y], fill=WHITE)
    # Door.
    door_w = base_w * 0.24
    door_h = base_h * 0.46
    door_left = cx - door_w / 2
    door_bottom = body_bottom_y
    door_top = door_bottom - door_h
    draw.rounded_rectangle(
        [door_left, door_top, door_left + door_w, door_bottom],
        radius=door_w * 0.18,
        fill=door_color,
    )


def render_icon(size: int, *, maskable: bool = False) -> Image.Image:
    """One icon at `size` px. maskable = full-bleed gradient with safe-zone content."""
    img = vertical_gradient(size, ORANGE_TOP, ORANGE_BOTTOM)
    draw = ImageDraw.Draw(img, "RGBA")

    if maskable:
        # Full-bleed square: the OS mask crops the edges, so the house sits
        # well inside the 80% safe zone.
        house_scale = 0.62
    else:
        # Rounded-square app icon with a little padding.
        radius = size * 0.22
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
        img.putalpha(mask)
        house_scale = 0.86

    draw_house(draw, size, house_scale, DOOR)
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rentora PWA icons.")
    parser.add_argument("--out", type=Path, default=Path("frontend/public/icons"), help="Output directory")
    args = parser.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    targets = {
        "icon-192.png": (192, False),
        "icon-512.png": (512, False),
        "maskable-512.png": (512, True),
        "apple-touch-180.png": (180, False),
        "favicon-32.png": (32, False),
        "favicon-48.png": (48, False),
        "favicon-96.png": (96, False),
        "favicon-144.png": (144, False),
    }

    for name, (size, maskable) in targets.items():
        render_icon(size, maskable=maskable).save(out / name, format="PNG", optimize=True)
        print(f"wrote {out / name} ({size}x{size}, maskable={maskable})")


if __name__ == "__main__":
    main()
