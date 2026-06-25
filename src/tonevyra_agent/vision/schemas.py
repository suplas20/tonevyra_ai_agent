"""Schema-validated structured vision analysis results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VisionIssues(BaseModel):
    """Issue summary produced by a vision backend."""

    model_config = ConfigDict(extra="allow")

    exposure: str
    color_cast: str
    haze: str | None = None
    haze_turbidity: str | None = None
    contrast: str
    sharpness: str
    noise: str
    skin_tone: str | None = None

    @field_validator("*")
    @classmethod
    def non_empty_issue_values(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("issue values must not be empty")
        return value


class VisionCorrectionIntents(BaseModel):
    """Numeric model suggestions for the planner to validate and clamp.

    These values are advisory evidence from the model. They are not final
    Lightroom settings until the Correction Planner validates them.
    """

    model_config = ConfigDict(extra="forbid")

    exposure: float | None = None
    contrast: float | None = None
    highlights: float | None = None
    shadows: float | None = None
    whites: float | None = None
    blacks: float | None = None
    temp: float | None = None
    temperature_delta: float | None = None
    tint: float | None = None
    vibrance: float | None = None
    saturation: float | None = None
    texture: float | None = None
    clarity: float | None = None
    dehaze: float | None = None
    noise_reduction: float | None = None
    sharpening: float | None = None
    red_saturation: float | None = None
    orange_saturation: float | None = None
    yellow_saturation: float | None = None
    green_saturation: float | None = None
    aqua_saturation: float | None = None
    blue_saturation: float | None = None
    purple_saturation: float | None = None
    magenta_saturation: float | None = None
    red_hue: float | None = None
    orange_hue: float | None = None
    yellow_hue: float | None = None
    green_hue: float | None = None
    aqua_hue: float | None = None
    blue_hue: float | None = None
    purple_hue: float | None = None
    magenta_hue: float | None = None
    red_luminance: float | None = None
    orange_luminance: float | None = None
    yellow_luminance: float | None = None
    green_luminance: float | None = None
    aqua_luminance: float | None = None
    blue_luminance: float | None = None
    purple_luminance: float | None = None
    magenta_luminance: float | None = None


class VisionAnalysisResult(BaseModel):
    """Validated output consumed later by the Correction Planner."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    model_backend: str
    model_name: str = "mock-fixture-v1"
    scene_type: str
    main_subject: str | None = None
    usable: bool
    issues: VisionIssues
    correction_intents: VisionCorrectionIntents | None = None
    edit_intent: str = "structured_numeric_correction"
    confidence: float = Field(ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)
    requires_review: bool = False

    @field_validator("scene_type", "edit_intent", "model_backend", "model_name")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @model_validator(mode="after")
    def derive_review_flag(self) -> VisionAnalysisResult:
        if self.confidence < 0.7 or "low_confidence" in self.risk_flags:
            self.requires_review = True
        return self

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_backend": self.model_backend,
            "model_name": self.model_name,
            "scene_type": self.scene_type,
            "main_subject": self.main_subject,
            "usable": self.usable,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
            "risk_flags": self.risk_flags,
            "issues": self.issues.model_dump(exclude_none=True),
            "correction_intents": self.correction_intents.model_dump(exclude_none=True)
            if self.correction_intents is not None
            else {},
        }
