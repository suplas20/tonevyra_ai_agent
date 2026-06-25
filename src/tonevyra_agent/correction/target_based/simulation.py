"""Stage 8 - bounded predictive simulation of a correction candidate.

The simulator applies directionally-correct approximations of Lightroom
adjustments to the preview pixels so the planner can re-measure a *predicted*
result and rank candidates. These are predictions, NOT real Lightroom renders;
the ground-truth result is still produced by the actual Lightroom export and
scored by the Quality Gate. The decision log records this explicitly.
"""

from __future__ import annotations

import cv2
import numpy as np

from tonevyra_agent.correction.target_based.measurement import _HUE_RANGES, measure_array
from tonevyra_agent.correction.target_based.schemas import ImageMeasurement


def predict_measurement(rgb: np.ndarray, adjustments: dict[str, float]) -> ImageMeasurement:
    """Apply a candidate to the preview and re-measure the predicted result."""

    predicted = predict_array(rgb, adjustments)
    return measure_array(predicted)


def predict_array(rgb: np.ndarray, adjustments: dict[str, float]) -> np.ndarray:
    """Return a predicted RGB uint8 array after applying bounded adjustments."""

    work = np.ascontiguousarray(rgb.astype(np.float32) / 255.0)

    work = _apply_white_balance(work, adjustments)
    work = _apply_exposure(work, adjustments)
    work = _apply_tone(work, adjustments)
    work = _apply_local_contrast(work, adjustments)
    work = _apply_saturation(work, adjustments)

    work = np.clip(work, 0.0, 1.0)
    return (work * 255.0 + 0.5).astype(np.uint8)


def _g(adjustments: dict[str, float], key: str) -> float:
    value = adjustments.get(key)
    return float(value) if value is not None else 0.0


def _luma(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]


def _scale_to_luma(rgb: np.ndarray, new_luma: np.ndarray, old_luma: np.ndarray) -> np.ndarray:
    """Scale RGB so its luma becomes new_luma while preserving hue ratios."""

    safe_old = np.maximum(old_luma, 1e-4)
    factor = np.clip(new_luma / safe_old, 0.0, 8.0)[:, :, None]
    return rgb * factor


def _apply_white_balance(rgb: np.ndarray, adj: dict[str, float]) -> np.ndarray:
    temp = _g(adj, "temperature_delta") / 3500.0  # +warm
    tint = _g(adj, "tint") / 50.0  # +magenta
    out = rgb.copy()
    out[:, :, 0] *= 1.0 + 0.30 * temp + 0.10 * tint  # red
    out[:, :, 1] *= 1.0 - 0.10 * tint  # green
    out[:, :, 2] *= 1.0 - 0.30 * temp + 0.10 * tint  # blue
    return out


def _apply_exposure(rgb: np.ndarray, adj: dict[str, float]) -> np.ndarray:
    exposure = _g(adj, "exposure")
    if exposure == 0.0:
        return rgb
    # Calibrated against a real Lightroom export pair (JWY00172): a +0.77 stop
    # moved mean luma x1.25 on the RAW render, NOT the x1.7 that a literal
    # 2**exposure on the sRGB preview implies. Using a gentler factor keeps the
    # planner from believing a weak exposure is enough (the under-correction bug).
    return rgb * float(1.0 + 0.34 * exposure)


def _apply_tone(rgb: np.ndarray, adj: dict[str, float]) -> np.ndarray:
    luma = _luma(rgb)
    new_luma = luma.copy()

    shadows = _g(adj, "shadows") / 100.0
    highlights = _g(adj, "highlights") / 100.0
    whites = _g(adj, "whites") / 100.0
    blacks = _g(adj, "blacks") / 100.0
    contrast = _g(adj, "contrast") / 100.0

    w_shadow = np.clip(1.0 - luma / 0.5, 0.0, 1.0)
    w_highlight = np.clip((luma - 0.5) / 0.5, 0.0, 1.0)
    w_black = np.clip(1.0 - luma / 0.25, 0.0, 1.0)
    w_white = np.clip((luma - 0.75) / 0.25, 0.0, 1.0)

    # Tonal gains calibrated down: on the real export pair, exposure alone
    # explained the luma change while shadow/highlight moves roughly canceled on
    # the mean. Over-strong tonal lift was a second source of over-prediction.
    new_luma = new_luma + 0.22 * shadows * w_shadow
    new_luma = new_luma + 0.22 * highlights * w_highlight
    new_luma = new_luma + 0.13 * whites * w_white
    new_luma = new_luma + 0.13 * blacks * w_black

    if contrast != 0.0:
        new_luma = (new_luma - 0.5) * (1.0 + contrast) + 0.5

    new_luma = np.clip(new_luma, 0.0, 4.0)
    return _scale_to_luma(rgb, new_luma, luma)


def _apply_local_contrast(rgb: np.ndarray, adj: dict[str, float]) -> np.ndarray:
    """Approximate dehaze/clarity: mild midtone contrast + slight chroma lift."""

    dehaze = _g(adj, "dehaze") / 100.0
    clarity = _g(adj, "clarity") / 100.0
    strength = 0.30 * dehaze + 0.20 * clarity
    if strength == 0.0:
        return rgb
    luma = _luma(rgb)
    new_luma = (luma - 0.5) * (1.0 + strength) + 0.5
    new_luma = np.clip(new_luma, 0.0, 4.0)
    return _scale_to_luma(rgb, new_luma, luma)


def _apply_saturation(rgb: np.ndarray, adj: dict[str, float]) -> np.ndarray:
    clipped = np.clip(rgb, 0.0, 1.0)
    hsv = cv2.cvtColor((clipped * 255.0 + 0.5).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1] / 255.0

    saturation = _g(adj, "saturation") / 100.0
    vibrance = _g(adj, "vibrance") / 100.0
    dehaze = _g(adj, "dehaze") / 100.0
    clarity = _g(adj, "clarity") / 100.0

    factor = np.full_like(sat, 1.0 + saturation)
    factor *= 1.0 + vibrance * (1.0 - sat)
    factor *= 1.0 + 0.15 * dehaze + 0.08 * clarity

    # Per-hue saturation: red wraps the hue circle.
    red_delta = _g(adj, "red_saturation") / 100.0
    if red_delta != 0.0:
        red_mask = (hue < 10.0) | (hue >= 165.0)
        factor[red_mask] *= 1.0 + red_delta
    for band, (low, high) in _HUE_RANGES.items():
        delta = _g(adj, f"{band}_saturation") / 100.0
        if delta == 0.0:
            continue
        band_mask = (hue >= low) & (hue < high)
        factor[band_mask] *= 1.0 + delta

    sat = np.clip(sat * np.clip(factor, 0.0, 4.0), 0.0, 1.0)
    hsv[:, :, 1] = sat * 255.0
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32) / 255.0
    return out
