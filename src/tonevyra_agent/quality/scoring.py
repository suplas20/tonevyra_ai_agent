"""Deterministic local image scoring for the Quality Gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, QualityDecision, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.quality.schemas import QualityScores, QualityThresholds, QualityWeights


def weights_from_settings(settings: Settings | None = None) -> QualityWeights:
    config = settings or get_settings()
    return QualityWeights(
        exposure=config.quality_exposure_weight,
        color=config.quality_color_weight,
        sharpness=config.quality_sharpness_weight,
        noise=config.quality_noise_weight,
        saturation=config.quality_saturation_weight,
        underwater_cast=config.quality_underwater_cast_weight,
    )


def thresholds_from_settings(settings: Settings | None = None) -> QualityThresholds:
    config = settings or get_settings()
    return QualityThresholds(
        pass_threshold=float(config.quality_pass_threshold),
        review_threshold=float(config.quality_review_threshold),
    )


def score_export_image(
    export_path: str | Path,
    *,
    settings: Settings | None = None,
    scene_type: str | None = None,
) -> tuple[QualityScores, dict[str, Any], list[str]]:
    """Score an exported image using bounded local heuristics.

    When ``scene_type`` indicates an underwater capture, color-balance, cast, and
    saturation tolerances are relaxed so naturally colorful underwater results are
    not penalized as if they were neutral studio scenes.
    """

    config = settings or get_settings()
    image = _load_rgb_array(export_path)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    weights = weights_from_settings(config)
    is_underwater = bool(scene_type) and "underwater" in scene_type.lower()

    saturation_ideal = config.quality_underwater_saturation_ideal if is_underwater else config.quality_saturation_ideal
    color_spread_scale = config.quality_underwater_color_spread_scale if is_underwater else config.quality_color_spread_scale
    cast_allowance = config.quality_underwater_cast_allowance if is_underwater else config.quality_cast_allowance

    exposure_score, exposure_metrics, exposure_reasons = _score_exposure(gray)
    color_score, color_metrics, color_reasons = _score_color_balance(image, spread_scale=color_spread_scale)
    sharpness_score, sharpness_metrics, sharpness_reasons = _score_sharpness(gray)
    noise_score, noise_metrics, noise_reasons = _score_noise(gray)
    saturation_score, saturation_metrics, saturation_reasons = _score_saturation(hsv, ideal=saturation_ideal)
    underwater_cast_score, underwater_metrics, underwater_reasons = _score_underwater_cast(image, allowance=cast_allowance)

    weighted_total = (
        exposure_score * weights.exposure
        + color_score * weights.color
        + sharpness_score * weights.sharpness
        + noise_score * weights.noise
        + saturation_score * weights.saturation
        + underwater_cast_score * weights.underwater_cast
    )
    overall_score = _bounded_score(weighted_total / weights.total)

    metrics = {
        "image": {
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        },
        "scene_profile": {
            "scene_type": scene_type,
            "is_underwater": is_underwater,
            "saturation_ideal": saturation_ideal,
            "color_spread_scale": color_spread_scale,
            "cast_allowance": cast_allowance,
        },
        "exposure": exposure_metrics,
        "color": color_metrics,
        "sharpness": sharpness_metrics,
        "noise": noise_metrics,
        "saturation": saturation_metrics,
        "underwater_cast": underwater_metrics,
    }
    reasons = [
        *exposure_reasons,
        *color_reasons,
        *sharpness_reasons,
        *noise_reasons,
        *saturation_reasons,
        *underwater_reasons,
    ]
    scores = QualityScores(
        exposure_score=exposure_score,
        color_score=color_score,
        sharpness_score=sharpness_score,
        noise_score=noise_score,
        saturation_score=saturation_score,
        underwater_cast_score=underwater_cast_score,
        overall_score=overall_score,
    )
    return scores, metrics, reasons


def decide_from_score(overall_score: float, *, thresholds: QualityThresholds) -> QualityDecision:
    if overall_score >= thresholds.pass_threshold:
        return QualityDecision.PASS
    if overall_score >= thresholds.review_threshold:
        return QualityDecision.REVIEW_REQUIRED
    return QualityDecision.FAILED


def _load_rgb_array(export_path: str | Path) -> np.ndarray:
    path = Path(export_path)
    if not path.exists():
        raise TonevyraError(
            code=ErrorCode.EXPORT_FILE_MISSING,
            message=f"Export file was not found: {path}",
            failed_stage=Stage.QUALITY.value,
        )

    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            return np.asarray(image, dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as exc:
        raise TonevyraError(
            code=ErrorCode.QUALITY_CHECK_FAILED,
            message=f"Unable to read exported image for quality scoring: {path}",
            failed_stage=Stage.QUALITY.value,
        ) from exc


def _score_exposure(gray: np.ndarray) -> tuple[float, dict[str, Any], list[str]]:
    mean_luma = float(gray.mean())
    clipped_shadow_ratio = float((gray <= 5).mean())
    clipped_highlight_ratio = float((gray >= 250).mean())
    mean_penalty = abs(mean_luma - 128.0) / 128.0 * 75.0
    clipping_penalty = min(35.0, (clipped_shadow_ratio + clipped_highlight_ratio) * 350.0)
    score = _bounded_score(100.0 - mean_penalty - clipping_penalty)
    reasons = []
    if score < 70:
        reasons.append("exposure score below review threshold")
    return score, {
        "mean_luma": round(mean_luma, 3),
        "clipped_shadow_ratio": round(clipped_shadow_ratio, 6),
        "clipped_highlight_ratio": round(clipped_highlight_ratio, 6),
    }, reasons


def _score_color_balance(image: np.ndarray, *, spread_scale: float = 90.0) -> tuple[float, dict[str, Any], list[str]]:
    channel_means = image.reshape(-1, 3).mean(axis=0)
    red_mean, green_mean, blue_mean = (float(value) for value in channel_means)
    spread = max(red_mean, green_mean, blue_mean) - min(red_mean, green_mean, blue_mean)
    score = _bounded_score(100.0 - spread / spread_scale * 100.0)
    reasons = []
    if score < 70:
        reasons.append("color channel balance is uneven")
    return score, {
        "red_mean": round(red_mean, 3),
        "green_mean": round(green_mean, 3),
        "blue_mean": round(blue_mean, 3),
        "channel_spread": round(spread, 3),
    }, reasons


def _score_sharpness(gray: np.ndarray) -> tuple[float, dict[str, Any], list[str]]:
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    score = _bounded_score(min(100.0, variance / 220.0 * 100.0))
    reasons = []
    if score < 70:
        reasons.append("sharpness score below review threshold")
    return score, {"laplacian_variance": round(variance, 3)}, reasons


def _score_noise(gray: np.ndarray) -> tuple[float, dict[str, Any], list[str]]:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    residual_std = float((gray.astype(np.float32) - blurred.astype(np.float32)).std())
    score = _bounded_score(100.0 - min(100.0, residual_std / 28.0 * 100.0))
    reasons = []
    if score < 70:
        reasons.append("high-frequency noise estimate is elevated")
    return score, {"residual_std": round(residual_std, 3)}, reasons


def _score_saturation(hsv: np.ndarray, *, ideal: float = 0.34) -> tuple[float, dict[str, Any], list[str]]:
    saturation_mean = float(hsv[:, :, 1].mean() / 255.0)
    score = _bounded_score(100.0 - abs(saturation_mean - ideal) / ideal * 80.0)
    reasons = []
    if score < 70:
        reasons.append("saturation is outside the target range")
    return score, {"mean_saturation": round(saturation_mean, 4)}, reasons


def _score_underwater_cast(image: np.ndarray, *, allowance: float = 12.0) -> tuple[float, dict[str, Any], list[str]]:
    channel_means = image.reshape(-1, 3).mean(axis=0)
    red_mean, green_mean, blue_mean = (float(value) for value in channel_means)
    blue_green_mean = (blue_mean + green_mean) / 2.0
    cast_delta = max(0.0, blue_green_mean - red_mean - allowance)
    score = _bounded_score(100.0 - min(100.0, cast_delta / 85.0 * 100.0))
    reasons = []
    if score < 70:
        reasons.append("blue-green underwater cast remains strong")
    return score, {
        "red_mean": round(red_mean, 3),
        "green_mean": round(green_mean, 3),
        "blue_mean": round(blue_mean, 3),
        "blue_green_minus_red": round(blue_green_mean - red_mean, 3),
    }, reasons


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)
