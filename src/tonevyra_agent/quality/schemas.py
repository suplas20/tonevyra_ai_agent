"""Schemas for deterministic exported-image quality results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tonevyra_agent.core.enums import QualityDecision


class QualityWeights(BaseModel):
    """Weighted contribution of each bounded score to the overall score."""

    model_config = ConfigDict(extra="forbid")

    exposure: float = Field(ge=0.0)
    color: float = Field(ge=0.0)
    sharpness: float = Field(ge=0.0)
    noise: float = Field(ge=0.0)
    saturation: float = Field(ge=0.0)
    underwater_cast: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_total_weight(self) -> "QualityWeights":
        if self.total <= 0:
            raise ValueError("quality weights must have a positive total")
        return self

    @property
    def total(self) -> float:
        return self.exposure + self.color + self.sharpness + self.noise + self.saturation + self.underwater_cast


class QualityThresholds(BaseModel):
    """Final decision thresholds for the quality gate."""

    model_config = ConfigDict(extra="forbid")

    pass_threshold: float = Field(ge=0.0, le=100.0)
    review_threshold: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_order(self) -> "QualityThresholds":
        if self.review_threshold > self.pass_threshold:
            raise ValueError("review threshold must be <= pass threshold")
        return self


class QualityScores(BaseModel):
    """Component scores required by the MVP quality gate contract."""

    model_config = ConfigDict(extra="forbid")

    exposure_score: float = Field(ge=0.0, le=100.0)
    color_score: float = Field(ge=0.0, le=100.0)
    sharpness_score: float = Field(ge=0.0, le=100.0)
    noise_score: float = Field(ge=0.0, le=100.0)
    saturation_score: float = Field(ge=0.0, le=100.0)
    underwater_cast_score: float = Field(ge=0.0, le=100.0)
    overall_score: float = Field(ge=0.0, le=100.0)


class QualityDetail(BaseModel):
    """Persisted quality_detail.json payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    task_id: str
    export_path: str
    scores: QualityScores
    decision: QualityDecision
    reason_summary: str
    reasons: list[str] = Field(default_factory=list)
    thresholds: QualityThresholds
    weights: QualityWeights
    metrics: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "export_path", "reason_summary")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value
