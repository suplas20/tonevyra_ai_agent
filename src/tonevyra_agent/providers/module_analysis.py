"""Deterministic local module analysis provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from tonevyra_agent.schemas.analysis import AnalysisRequest, AnalysisResult


class ModuleAnalysisProvider:
    """Analyze the generated preview using local image statistics only."""

    provider_type = "module"
    provider_version = "module-analysis-v1"

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        image = _load_rgb(request.preview_path)
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

        luma_mean = float(gray.mean())
        luma_p10 = float(np.percentile(gray, 10))
        luma_p90 = float(np.percentile(gray, 90))
        clipped_shadow_ratio = float((gray <= 5).mean())
        clipped_highlight_ratio = float((gray >= 250).mean())
        red_mean, green_mean, blue_mean = (float(value) for value in image.reshape(-1, 3).mean(axis=0))
        channel_spread = max(red_mean, green_mean, blue_mean) - min(red_mean, green_mean, blue_mean)
        saturation_mean = float(hsv[:, :, 1].mean() / 255.0)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        noise = float((gray.astype(np.float32) - blurred.astype(np.float32)).std())

        exposure = _exposure_label(luma_mean, clipped_shadow_ratio, clipped_highlight_ratio)
        contrast = _contrast_label(luma_p10, luma_p90)
        color_cast = _color_cast_label(red_mean, green_mean, blue_mean)
        sharpness_label = _sharpness_label(sharpness)
        noise_label = _noise_label(noise)
        scene = _scene_label(color_cast=color_cast, saturation=saturation_mean, metadata=request.metadata)
        risks = _risk_flags(
            exposure=exposure,
            color_cast=color_cast,
            clipped_shadow_ratio=clipped_shadow_ratio,
            clipped_highlight_ratio=clipped_highlight_ratio,
            sharpness_label=sharpness_label,
            noise_label=noise_label,
        )

        return AnalysisResult(
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            provider_type=self.provider_type,
            provider_version=self.provider_version,
            scene={"type": scene, "source": "module_statistics"},
            subjects=_subjects_from_metadata(request.metadata),
            technical_findings=[
                {
                    "code": "EXPOSURE",
                    "value": exposure,
                    "mean_luma": round(luma_mean, 3),
                    "clipped_shadow_ratio": round(clipped_shadow_ratio, 6),
                    "clipped_highlight_ratio": round(clipped_highlight_ratio, 6),
                },
                {"code": "CONTRAST", "value": contrast, "luma_p10": round(luma_p10, 3), "luma_p90": round(luma_p90, 3)},
                {"code": "SHARPNESS", "value": sharpness_label, "laplacian_variance": round(sharpness, 3)},
                {"code": "NOISE", "value": noise_label, "noise_residual_std": round(noise, 3)},
                {"code": "HAZE", "value": "none"},
            ],
            color_findings=[
                {
                    "code": "COLOR_CAST",
                    "value": color_cast,
                    "red_mean": round(red_mean, 3),
                    "green_mean": round(green_mean, 3),
                    "blue_mean": round(blue_mean, 3),
                    "channel_spread": round(channel_spread, 3),
                },
                {"code": "SATURATION", "value": _saturation_label(saturation_mean), "mean_saturation": round(saturation_mean, 4)},
            ],
            quality_risks=risks,
            confidence=0.82,
            analysis_evidence={
                "image": {
                    "width": int(image.shape[1]),
                    "height": int(image.shape[0]),
                },
                "plan": request.plan,
            },
        )


def analysis_to_vision_payload(result: AnalysisResult) -> dict[str, Any]:
    """Adapt normalized T-021 analysis into the current planner's vision schema."""

    main_subject = str(result.subjects[0].get("type")) if result.subjects else None
    return {
        "schema_version": "1.0",
        "model_backend": "module",
        "model_name": result.provider_version,
        "scene_type": str(result.scene.get("type") or result.scene.get("genre") or "general_photo"),
        "main_subject": main_subject,
        "usable": "source_focus_failure" not in _risk_labels(result.quality_risks),
        "issues": {
            "exposure": _finding_value(result.technical_findings, "EXPOSURE", "normal"),
            "color_cast": _finding_value(result.color_findings, "COLOR_CAST", "neutral"),
            "haze": _finding_value(result.technical_findings, "HAZE", "none"),
            "contrast": _finding_value(result.technical_findings, "CONTRAST", "normal"),
            "sharpness": _finding_value(result.technical_findings, "SHARPNESS", "acceptable"),
            "noise": _finding_value(result.technical_findings, "NOISE", "low"),
            "skin_tone": None,
        },
        "edit_intent": "natural_clean",
        "confidence": result.confidence,
        "risk_flags": _risk_labels(result.quality_risks),
        "requires_review": result.confidence < 0.7,
    }


def _load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.uint8)


def _finding_value(findings: list[dict[str, Any]], code: str, default: str) -> str:
    for finding in findings:
        if finding.get("code") == code:
            return str(finding.get("value", default))
    return default


def _risk_labels(risks: list[Any]) -> list[str]:
    labels: list[str] = []
    for risk in risks:
        if isinstance(risk, dict):
            label = str(risk.get("code") or risk.get("type") or risk.get("label") or "").lower()
            if label:
                labels.append(label)
        else:
            labels.append(str(risk))
    return labels


def _exposure_label(mean_luma: float, clipped_shadow_ratio: float, clipped_highlight_ratio: float) -> str:
    if clipped_highlight_ratio > 0.08 or mean_luma > 205:
        return "overexposed"
    if clipped_shadow_ratio > 0.22 or mean_luma < 38:
        return "severely_underexposed"
    if clipped_shadow_ratio > 0.12 or mean_luma < 55:
        return "underexposed"
    if mean_luma < 92:
        return "slightly_underexposed"
    if mean_luma > 168:
        return "slightly_overexposed"
    return "normal"


def _contrast_label(p10: float, p90: float) -> str:
    spread = p90 - p10
    if spread < 55:
        return "low"
    if spread > 190:
        return "high"
    return "normal"


def _color_cast_label(red: float, green: float, blue: float) -> str:
    if red - max(green, blue) > 32:
        return "warm"
    if blue - max(red, green) > 42:
        return "cool_blue"
    if ((blue + green) / 2.0) - red > 45 and blue > red and green > red:
        return "blue_green"
    if green - max(red, blue) > 35:
        return "green"
    return "neutral"


def _saturation_label(value: float) -> str:
    if value > 0.72:
        return "high"
    if value < 0.12:
        return "low"
    return "normal"


def _sharpness_label(value: float) -> str:
    if value < 70:
        return "soft"
    return "acceptable"


def _noise_label(value: float) -> str:
    if value > 18:
        return "high"
    if value > 10:
        return "medium"
    return "low"


def _scene_label(*, color_cast: str, saturation: float, metadata: dict[str, Any]) -> str:
    file_name = str(metadata.get("file", {}).get("name", "")).lower()
    if "underwater" in file_name:
        return "underwater_candidate"
    if color_cast == "blue_green" and saturation < 0.65:
        return "underwater_candidate"
    return "general_photo"


def _subjects_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    file_name = str(metadata.get("file", {}).get("name", "")).lower()
    if "portrait" in file_name:
        return [{"type": "person", "priority": 1}]
    return []


def _risk_flags(
    *,
    exposure: str,
    color_cast: str,
    clipped_shadow_ratio: float,
    clipped_highlight_ratio: float,
    sharpness_label: str,
    noise_label: str,
) -> list[str]:
    flags: list[str] = []
    if exposure in {"severely_underexposed", "underexposed", "overexposed"}:
        flags.append(exposure)
    if clipped_shadow_ratio > 0.18 or clipped_highlight_ratio > 0.12:
        flags.append("source_irrecoverable_clipping")
    if color_cast not in {"neutral"}:
        flags.append(f"{color_cast}_cast")
    if sharpness_label == "soft":
        flags.append("blur_detected")
    if noise_label == "high":
        flags.append("noise_elevated")
    return flags
