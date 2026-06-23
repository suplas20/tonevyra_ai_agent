"""Correction Planner schemas and Lightroom adjustment safety contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


ADJUSTMENT_RANGES: dict[str, tuple[float, float]] = {
    "exposure": (-2.0, 2.0),
    "contrast": (-50.0, 50.0),
    "highlights": (-80.0, 40.0),
    "shadows": (-40.0, 80.0),
    "whites": (-50.0, 50.0),
    "blacks": (-50.0, 50.0),
    "temperature_delta": (-3500.0, 3500.0),
    "tint": (-50.0, 50.0),
    "vibrance": (-30.0, 60.0),
    "saturation": (-30.0, 30.0),
    "texture": (-20.0, 35.0),
    "clarity": (-20.0, 35.0),
    "dehaze": (0.0, 35.0),
    "noise_reduction": (0.0, 60.0),
    "sharpening": (0.0, 80.0),
}


class CorrectionPlan(BaseModel):
    """Safe Lightroom adjustment plan produced by the Correction Planner."""

    model_config = ConfigDict(extra="forbid")

    planner_version: str = "rule-planner-v1"
    base_preset: str
    style_target: str
    adjustments_json: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_review: bool = False
    clamped: bool = False
    reason_summary: str
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_preset", "style_target", "reason_summary", "planner_version")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("adjustments_json")
    @classmethod
    def supported_and_in_range_adjustments(cls, value: dict[str, float]) -> dict[str, float]:
        for key, adjustment in value.items():
            if key not in ADJUSTMENT_RANGES:
                raise ValueError(f"unsupported Lightroom adjustment: {key}")
            minimum, maximum = ADJUSTMENT_RANGES[key]
            if adjustment < minimum or adjustment > maximum:
                raise ValueError(f"adjustment {key}={adjustment} outside range {minimum}..{maximum}")
        return value

    def summary(self) -> dict[str, Any]:
        return {
            "planner_version": self.planner_version,
            "base_preset": self.base_preset,
            "style_target": self.style_target,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
            "clamped": self.clamped,
            "reason_summary": self.reason_summary,
            "adjustments_json": self.adjustments_json,
            "source": self.source,
        }
