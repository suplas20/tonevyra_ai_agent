"""Analyze expert before/after photo pairs for local planner calibration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES


class ImageStyleMetrics(BaseModel):
    """Global image statistics used as local-only learning evidence."""

    model_config = ConfigDict(extra="forbid")

    luma_mean: float
    luma_contrast: float
    saturation_mean: float
    value_mean: float
    warmth: float
    magenta_green: float
    local_contrast: float
    shadow_ratio: float
    highlight_ratio: float


class ExpertReferencePairAnalysis(BaseModel):
    """Structured evidence extracted from one expert before/after pair."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "tonevyra.expert_reference_pair.v1"
    original_path: str
    corrected_path: str
    original_metrics: ImageStyleMetrics
    corrected_metrics: ImageStyleMetrics
    metric_delta: dict[str, float]
    suggested_lightroom_delta: dict[str, float]
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "confidence": self.confidence,
            "reason_summary": self.reason_summary,
            "suggested_lightroom_delta": self.suggested_lightroom_delta,
            "metric_delta": self.metric_delta,
        }


@dataclass(frozen=True)
class ReferencePairPaths:
    original_path: Path
    corrected_path: Path


def analyze_expert_reference_pair(original_path: Path, corrected_path: Path) -> ExpertReferencePairAnalysis:
    """Convert an expert-edited before/after pair into bounded Lightroom-style deltas.

    The output is evidence for planner calibration and user style learning. It is
    not a direct edit command and does not fine-tune a model at runtime.
    """

    paths = ReferencePairPaths(original_path=original_path.resolve(), corrected_path=corrected_path.resolve())
    _validate_pair_paths(paths)

    original = _load_rgb_array(paths.original_path)
    corrected = _load_rgb_array(paths.corrected_path, target_size=(original.shape[1], original.shape[0]))

    before = _compute_metrics(original)
    after = _compute_metrics(corrected)
    metric_delta = _metric_delta(before, after)
    suggested = _suggest_lightroom_delta(metric_delta)
    confidence = _confidence_from_delta(metric_delta, suggested)

    return ExpertReferencePairAnalysis(
        original_path=str(paths.original_path),
        corrected_path=str(paths.corrected_path),
        original_metrics=before,
        corrected_metrics=after,
        metric_delta=metric_delta,
        suggested_lightroom_delta=suggested,
        confidence=confidence,
        reason_summary=_reason_summary(metric_delta, suggested),
    )


def _validate_pair_paths(paths: ReferencePairPaths) -> None:
    for path in (paths.original_path, paths.corrected_path):
        if not path.exists() or not path.is_file():
            raise ValueError(f"reference pair image does not exist: {path}")


def _load_rgb_array(path: Path, target_size: tuple[int, int] | None = None) -> np.ndarray:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if target_size is not None and rgb.size != target_size:
            rgb = rgb.resize(target_size, Image.Resampling.LANCZOS)
        return np.asarray(rgb, dtype=np.uint8)


def _compute_metrics(rgb: np.ndarray) -> ImageStyleMetrics:
    rgb_float = rgb.astype(np.float32) / 255.0
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0

    l_channel = lab[:, :, 0] * (100.0 / 255.0)
    saturation = hsv[:, :, 1] / 255.0
    value = hsv[:, :, 2] / 255.0
    red = rgb_float[:, :, 0]
    green = rgb_float[:, :, 1]
    blue = rgb_float[:, :, 2]
    laplacian = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)

    return ImageStyleMetrics(
        luma_mean=round(float(np.mean(l_channel)), 6),
        luma_contrast=round(float(np.std(l_channel)), 6),
        saturation_mean=round(float(np.mean(saturation)), 6),
        value_mean=round(float(np.mean(value)), 6),
        warmth=round(float(np.mean(red - blue)), 6),
        magenta_green=round(float(np.mean(((red + blue) / 2.0) - green)), 6),
        local_contrast=round(float(np.var(laplacian)), 6),
        shadow_ratio=round(float(np.mean(value < 0.16)), 6),
        highlight_ratio=round(float(np.mean(value > 0.88)), 6),
    )


def _metric_delta(before: ImageStyleMetrics, after: ImageStyleMetrics) -> dict[str, float]:
    before_data = before.model_dump()
    after_data = after.model_dump()
    return {key: round(float(after_data[key]) - float(before_data[key]), 6) for key in before_data}


def _suggest_lightroom_delta(metric_delta: dict[str, float]) -> dict[str, float]:
    luma_delta = metric_delta["luma_mean"]
    contrast_delta = metric_delta["luma_contrast"]
    saturation_delta = metric_delta["saturation_mean"]
    value_delta = metric_delta["value_mean"]
    warmth_delta = metric_delta["warmth"]
    magenta_delta = metric_delta["magenta_green"]
    local_contrast_delta = metric_delta["local_contrast"]
    shadow_delta = metric_delta["shadow_ratio"]
    highlight_delta = metric_delta["highlight_ratio"]

    suggested = {
        "exposure": luma_delta * 0.032,
        "contrast": contrast_delta * 1.8,
        "highlights": _highlights_delta(highlight_delta, luma_delta),
        "shadows": _shadows_delta(shadow_delta, luma_delta, value_delta),
        "whites": highlight_delta * 90.0,
        "blacks": -shadow_delta * 90.0,
        "temperature_delta": warmth_delta * 2600.0,
        "tint": magenta_delta * 70.0,
        "vibrance": saturation_delta * 135.0,
        "saturation": saturation_delta * 75.0,
        "texture": local_contrast_delta * 22.0,
        "clarity": (contrast_delta * 0.35) + (local_contrast_delta * 24.0),
        "dehaze": max(0.0, contrast_delta * 0.22),
        "noise_reduction": 0.0,
        "sharpening": max(0.0, local_contrast_delta * 42.0),
    }
    return {key: _clamp_adjustment(key, value) for key, value in suggested.items()}


def _highlights_delta(highlight_delta: float, luma_delta: float) -> float:
    if highlight_delta > 0.015 and luma_delta > 0:
        return -highlight_delta * 120.0
    return highlight_delta * 60.0


def _shadows_delta(shadow_delta: float, luma_delta: float, value_delta: float) -> float:
    if shadow_delta < -0.01 or luma_delta > 1.0 or value_delta > 0.01:
        return abs(shadow_delta) * 120.0 + max(0.0, luma_delta * 0.7)
    return -shadow_delta * 60.0


def _clamp_adjustment(key: str, value: float) -> float:
    minimum, maximum = ADJUSTMENT_RANGES[key]
    return round(max(minimum, min(maximum, float(value))), 3)


def _confidence_from_delta(metric_delta: dict[str, float], suggested: dict[str, float]) -> float:
    signal = (
        abs(metric_delta["luma_mean"]) / 8.0
        + abs(metric_delta["luma_contrast"]) / 8.0
        + abs(metric_delta["saturation_mean"]) / 0.12
        + abs(metric_delta["warmth"]) / 0.08
        + abs(metric_delta["local_contrast"]) / 0.08
    )
    non_zero_adjustments = sum(1 for value in suggested.values() if abs(value) >= 0.05)
    return round(max(0.05, min(0.95, (signal / 5.0) + (non_zero_adjustments * 0.02))), 3)


def _reason_summary(metric_delta: dict[str, float], suggested: dict[str, float]) -> str:
    reasons: list[str] = []
    if suggested["exposure"] > 0.05:
        reasons.append("expert edit brightens global exposure")
    elif suggested["exposure"] < -0.05:
        reasons.append("expert edit darkens global exposure")
    if suggested["contrast"] > 2:
        reasons.append("expert edit increases contrast")
    elif suggested["contrast"] < -2:
        reasons.append("expert edit softens contrast")
    if suggested["temperature_delta"] > 80:
        reasons.append("expert edit warms color temperature")
    elif suggested["temperature_delta"] < -80:
        reasons.append("expert edit cools color temperature")
    if suggested["vibrance"] > 2 or suggested["saturation"] > 2:
        reasons.append("expert edit increases color intensity")
    elif suggested["vibrance"] < -2 or suggested["saturation"] < -2:
        reasons.append("expert edit reduces color intensity")
    if suggested["clarity"] > 2 or suggested["sharpening"] > 2:
        reasons.append("expert edit increases micro-contrast/detail")
    if abs(metric_delta["highlight_ratio"]) > 0.015:
        reasons.append("expert edit changes highlight distribution")
    if abs(metric_delta["shadow_ratio"]) > 0.015:
        reasons.append("expert edit changes shadow distribution")
    return "; ".join(reasons) if reasons else "expert pair has low global correction signal"
