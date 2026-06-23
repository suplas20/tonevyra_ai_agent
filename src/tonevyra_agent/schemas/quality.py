"""T-021 normalized quality schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tonevyra_agent.schemas.analysis import AnalysisResult, utc_now


QualityStatus = Literal["APPROVED", "RETRY_REQUIRED", "SOURCE_LIMITED", "TECHNICAL_FAILED", "FINAL_FAILED"]


class QualityRequest(BaseModel):
    """Input passed to a QualityProvider after T-020 export evidence is valid."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    attempt_id: str
    source_path: Path
    export_path: Path
    analysis: AnalysisResult
    applied_adjustment_plan: dict[str, Any] = Field(default_factory=dict)
    previous_quality_result: dict[str, Any] | None = None
    plan: str = "t021_mvp"

    @field_validator("job_id", "attempt_id", "plan")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class RetryRecommendation(BaseModel):
    """Provider recommendation; final retry permission belongs to RetryController."""

    model_config = ConfigDict(extra="forbid")

    recommended: bool = False
    strategy: str | None = None
    expected_gain: float = Field(default=0.0, ge=0.0, le=1.0)


class T021QualityResult(BaseModel):
    """Provider-neutral T-021 quality result."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t021.quality.result.v1"] = "t021.quality.result.v1"
    job_id: str
    attempt_id: str
    provider_type: Literal["module", "model"]
    status: QualityStatus
    scores: dict[str, float] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    retry_recommendation: RetryRecommendation = Field(default_factory=RetryRecommendation)
    source_limit_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    improvement_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)

    @field_validator("job_id", "attempt_id")
    @classmethod
    def non_empty_result_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value
