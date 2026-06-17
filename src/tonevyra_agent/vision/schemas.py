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
    edit_intent: str
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
        }
