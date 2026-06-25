"""Stage 1 - quantitative measurement of the preview image.

This module deliberately re-implements its own bounded heuristics instead of
importing :mod:`tonevyra_agent.quality.scoring`. The Correction Planner and the
Quality Gate are sibling layers; keeping measurement local avoids a
correction -> quality dependency while reusing the same proven techniques
(numpy + OpenCV) already accepted in this project.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.target_based.schemas import HUE_BANDS, HueStat, ImageMeasurement


# OpenCV hue is 0-179. Bands are inclusive-low, exclusive-high except the red wrap.
_HUE_RANGES: dict[str, tuple[float, float]] = {
    "orange": (10.0, 22.0),
    "yellow": (22.0, 33.0),
    "green": (33.0, 78.0),
    "aqua": (78.0, 96.0),
    "blue": (96.0, 126.0),
    "purple": (126.0, 145.0),
    "magenta": (145.0, 165.0),
}
_COLORED_SATURATION_THRESHOLD = 0.12
_MAX_EDGE = 1024


def measure_preview(preview_path: str | Path) -> ImageMeasurement:
    """Load a preview image and return its quantitative measurement."""

    rgb = _load_rgb_array(preview_path)
    return measure_array(rgb)


def measure_array(rgb: np.ndarray) -> ImageMeasurement:
    """Measure an already-loaded RGB uint8 array."""

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("measure_array expects an HxWx3 RGB array")
    rgb = np.ascontiguousarray(rgb.astype(np.uint8))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

    mean_luma = float(gray.mean())
    luma_p05, luma_p50, luma_p95 = (float(v) for v in np.percentile(gray, [5, 50, 95]))
    contrast_std = float(gray.std())
    clipped_shadow_ratio = float((gray <= 5).mean())
    clipped_highlight_ratio = float((gray >= 250).mean())

    channel_means = rgb.reshape(-1, 3).mean(axis=0)
    red_mean, green_mean, blue_mean = (float(v) for v in channel_means)
    channel_spread = float(max(channel_means) - min(channel_means))
    blue_green_minus_red = float((blue_mean + green_mean) / 2.0 - red_mean)

    hue = hsv[:, :, 0].astype(np.float32)
    sat = hsv[:, :, 1].astype(np.float32) / 255.0
    mean_saturation = float(sat.mean())

    total_pixels = float(sat.size)
    colored_mask = sat > _COLORED_SATURATION_THRESHOLD
    colored_pixel_ratio = float(colored_mask.mean())

    hue_stats = _hue_stats(hue=hue, sat=sat, colored_mask=colored_mask, total_pixels=total_pixels)
    dominant_hue, dominant_stat = max(
        hue_stats.items(), key=lambda item: item[1].coverage
    )

    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    noise_residual_std = float((gray.astype(np.float32) - blurred.astype(np.float32)).std())

    return ImageMeasurement(
        width=int(rgb.shape[1]),
        height=int(rgb.shape[0]),
        mean_luma=round(mean_luma, 3),
        luma_p05=round(luma_p05, 3),
        luma_p50=round(luma_p50, 3),
        luma_p95=round(luma_p95, 3),
        contrast_std=round(contrast_std, 3),
        clipped_shadow_ratio=round(clipped_shadow_ratio, 6),
        clipped_highlight_ratio=round(clipped_highlight_ratio, 6),
        red_mean=round(red_mean, 3),
        green_mean=round(green_mean, 3),
        blue_mean=round(blue_mean, 3),
        channel_spread=round(channel_spread, 3),
        blue_green_minus_red=round(blue_green_minus_red, 3),
        mean_saturation=round(mean_saturation, 4),
        colored_pixel_ratio=round(colored_pixel_ratio, 4),
        dominant_hue=dominant_hue,
        dominant_hue_coverage=round(dominant_stat.coverage, 4),
        hue_stats=hue_stats,
        sharpness_laplacian_var=round(sharpness, 3),
        noise_residual_std=round(noise_residual_std, 3),
    )


def _hue_stats(
    *,
    hue: np.ndarray,
    sat: np.ndarray,
    colored_mask: np.ndarray,
    total_pixels: float,
) -> dict[str, HueStat]:
    stats: dict[str, HueStat] = {}
    # Red wraps around the hue circle: [0,10) U [165,180).
    red_mask = colored_mask & ((hue < 10.0) | (hue >= 165.0))
    stats["red"] = _band_stat(mask=red_mask, sat=sat, total_pixels=total_pixels)
    for band, (low, high) in _HUE_RANGES.items():
        band_mask = colored_mask & (hue >= low) & (hue < high)
        stats[band] = _band_stat(mask=band_mask, sat=sat, total_pixels=total_pixels)
    # Guarantee every canonical band exists in the output.
    for band in HUE_BANDS:
        stats.setdefault(band, HueStat(coverage=0.0, mean_saturation=0.0))
    return stats


def _band_stat(*, mask: np.ndarray, sat: np.ndarray, total_pixels: float) -> HueStat:
    count = float(mask.sum())
    coverage = count / total_pixels if total_pixels else 0.0
    mean_sat = float(sat[mask].mean()) if count > 0 else 0.0
    return HueStat(coverage=min(1.0, coverage), mean_saturation=min(1.0, mean_sat))


def _load_rgb_array(preview_path: str | Path) -> np.ndarray:
    path = Path(preview_path)
    if not path.exists():
        raise TonevyraError(
            code=ErrorCode.CORRECTION_PLAN_FAILED,
            message=f"Preview image for measurement was not found: {path}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.Resampling.LANCZOS)
            return np.asarray(image, dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as exc:
        raise TonevyraError(
            code=ErrorCode.CORRECTION_PLAN_FAILED,
            message=f"Unable to read preview image for measurement: {path}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        ) from exc
