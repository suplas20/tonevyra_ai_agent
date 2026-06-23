"""T-021 job and attempt schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tonevyra_agent.schemas.analysis import utc_now


T021State = Literal[
    "CREATED",
    "ANALYZING",
    "ADJUSTMENT_READY",
    "LIGHTROOM_PROCESSING",
    "EXPORTED",
    "EVALUATING",
    "RETRY_REQUIRED",
    "APPROVED",
    "SOURCE_LIMITED",
    "TECHNICAL_FAILED",
    "FINAL_FAILED",
]


class JobEnvelope(BaseModel):
    """Compatibility-mode T-021 job envelope stored as artifact/event evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t021.job.v1"] = "t021.job.v1"
    job_id: str
    task_id: str
    plan: str = "t021_mvp"
    analysis_provider: Literal["module", "model"] = "module"
    quality_provider: Literal["module", "model"] = "module"
    state: T021State = "CREATED"
    attempt_no: int = Field(default=0, ge=0)
    max_quality_retries: int = Field(default=2, ge=0)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class AttemptContext(BaseModel):
    """Per-attempt identity and retry context."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    task_id: str
    attempt_id: str
    attempt_no: int = Field(ge=0)
    parent_attempt_id: str | None = None
    plan: str = "t021_mvp"
    previous_overall_score: float | None = None
