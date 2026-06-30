#!/usr/bin/env python3
"""Generate T-030 Windows tray ICO assets from the approved Tonevyra symbol."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "resources" / "branding" / "source" / "tonevyra_symbol.svg"
OUT = ROOT / "resources" / "branding" / "windows"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
TEAL = (0, 194, 183, 255)
TEAL_DARK = (0, 154, 151, 255)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def draw_symbol(size: int, badge: str | None = None) -> Image.Image:
    scale = size / 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx = cy = size * 0.48
    radius = size * 0.30
    gap = 8
    width = max(2, int(size * 0.018))

    for index in range(6):
        start = index * 60 + gap
        end = (index + 1) * 60 - gap
        color = _blend(TEAL, TEAL_DARK, index / 6)
        box = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.pieslice(box, start=start, end=end, fill=color)
        # Aperture blade cut, drawn transparent with alpha compositing.
        cut = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        cut_draw = ImageDraw.Draw(cut)
        angle = math.radians(start + 6)
        p1 = (cx, cy)
        p2 = (cx + math.cos(angle) * radius * 1.15, cy + math.sin(angle) * radius * 1.15)
        p3 = (cx + math.cos(angle + 0.14) * radius * 0.45, cy + math.sin(angle + 0.14) * radius * 0.45)
        cut_draw.polygon([p1, p2, p3], fill=(0, 0, 0, 255))
        alpha = image.getchannel("A")
        alpha.paste(Image.composite(Image.new("L", (size, size), 0), alpha, cut.getchannel("A")))
        image.putalpha(alpha)

    # Sparkle.
    star_cx = size * 0.78
    star_cy = size * 0.24
    long_r = size * 0.09
    short_r = size * 0.028
    star = []
    for i in range(8):
        r = long_r if i % 2 == 0 else short_r
        angle = -math.pi / 2 + i * math.pi / 4
        star.append((star_cx + math.cos(angle) * r, star_cy + math.sin(angle) * r))
    draw.polygon(star, fill=TEAL)

    if badge:
        _draw_badge(draw, size, badge)

    return image


def _draw_badge(draw: ImageDraw.ImageDraw, size: int, badge: str) -> None:
    r = max(4, int(size * 0.11))
    x = size - r - max(1, int(size * 0.03))
    y = size - r - max(1, int(size * 0.03))
    colors = {
        "processing": (41, 121, 255, 255),
        "warning": (255, 176, 0, 255),
        "error": (230, 57, 70, 255),
    }
    draw.ellipse([x - r, y - r, x + r, y + r], fill=colors[badge], outline=(255, 255, 255, 230), width=max(1, int(size * 0.02)))


def _blend(a: tuple[int, int, int, int], b: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(4))


def save_ico(name: str, badge: str | None = None) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    base = draw_symbol(256, badge)
    path = OUT / name
    base.save(path, sizes=[(size, size) for size in SIZES])
    return path


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"missing source asset: {SOURCE}")
    icons = {
        "watching": save_ico("tonevyra_tray.ico"),
        "processing": save_ico("tonevyra_tray_processing.ico", "processing"),
        "warning": save_ico("tonevyra_tray_warning.ico", "warning"),
        "error": save_ico("tonevyra_tray_error.ico", "error"),
    }
    manifest = {
        "schema_version": "t030.tray_icon_manifest.v1",
        "source_asset": "resources/branding/source/tonevyra_symbol.svg",
        "source_sha256": sha256(SOURCE),
        "sizes": SIZES,
        "icons": {
            key: {
                "path": str(path.relative_to(ROOT).as_posix()),
                "sha256": sha256(path),
            }
            for key, path in icons.items()
        },
        "approved_source": True,
        "notes": "Generated from the user-approved Tonevyra aperture symbol with transparent background.",
    }
    manifest_path = OUT / "tray_icon_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"OK: wrote tray icons to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
