"""T-021 normalized analysis schemas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FORBIDDEN_ANALYSIS_FIELDS = {
    "lightroom_adjustments",
    "develop_settings",
    "preset_path",
    "execute_command",
    "plugin_command",
    "final_decision",
    "final_status",
    "force_state_transition",
}


class AnalysisRequest(BaseModel):
    """Input passed to an AnalysisProvider."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    attempt_id: str
    preview_path: Path
    metadata: dict[str, Any] = Field(default_factory=dict)
    plan: str = "t021_mvp"
    previous_attempt_context: dict[str, Any] | None = None

    @field_validator("job_id", "attempt_id", "plan")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class AnalysisResult(BaseModel):
    """Provider-neutral analysis evidence consumed by the planner layer."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t021.analysis.result.v1"] = "t021.analysis.result.v1"
    job_id: str
    attempt_id: str
    provider_type: Literal["module", "model"]
    provider_version: str
    scene: dict[str, Any]
    subjects: list[dict[str, Any]] = Field(default_factory=list)
    technical_findings: list[dict[str, Any]]
    color_findings: list[dict[str, Any]]
    quality_risks: list[Any] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    analysis_evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")

    @field_validator("job_id", "attempt_id", "provider_version")
    @classmethod
    def non_empty_result_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("scene")
    @classmethod
    def scene_has_type(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not str(value.get("type") or value.get("genre") or "").strip():
            raise ValueError("scene.type or scene.genre must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_direct_adjustment_bypass(cls, data: Any) -> Any:
        forbidden = _find_forbidden_fields(data)
        if forbidden:
            raise ValueError(f"analysis provider output bypasses planner: {forbidden}")
        return data


def _find_forbidden_fields(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_ANALYSIS_FIELDS:
                found.append(child_path)
            found.extend(_find_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_fields(child, f"{prefix}[{index}]"))
    return found


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
