"""T-024 batch and photo set consistency schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BATCH_JOB_SCHEMA_VERSION = "t024.batch.job.v1"
SET_CONSISTENCY_SCHEMA_VERSION = "t024.set.consistency.v1"
RUNTIME_EVIDENCE_SCHEMA_VERSION = "t024.runtime.evidence.v1"

DEFAULT_CHUNK_SIZE = 10
MAX_MVP_CHUNK_SIZE = 10

BatchState = Literal[
    "CREATED",
    "GROUPING",
    "PROCESSING",
    "EVALUATING",
    "COMPLETED",
    "PARTIAL_FAILED",
    "FAILED",
]

ItemState = Literal[
    "QUEUED",
    "PROCESSING",
    "APPROVED",
    "SOURCE_LIMITED",
    "TECHNICAL_FAILED",
    "FINAL_FAILED",
    "PASS",
    "REVIEW_REQUIRED",
    "FAILED",
    "SKIPPED",
]

TERMINAL_ITEM_STATES = {
    "APPROVED",
    "SOURCE_LIMITED",
    "TECHNICAL_FAILED",
    "FINAL_FAILED",
    "PASS",
    "REVIEW_REQUIRED",
    "FAILED",
    "SKIPPED",
}

FAILED_ITEM_STATES = {"TECHNICAL_FAILED", "FINAL_FAILED", "FAILED"}


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class BatchItem(BaseModel):
    """One independently resumable photo item inside a batch."""

    model_config = ConfigDict(extra="allow")

    job_id: str
    source_path: str
    item_state: ItemState | str = "QUEUED"
    idempotency_key: str
    set_id: str | None = None
    attempt_id: str | None = None
    attempt_no: int = Field(default=0, ge=0)
    quality_retry_count: int = Field(default=0, ge=0)
    max_quality_retries: int = Field(default=2, ge=0)

    @field_validator("job_id", "source_path", "idempotency_key")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @property
    def is_terminal(self) -> bool:
        return self.item_state in TERMINAL_ITEM_STATES

    @property
    def is_failed(self) -> bool:
        return self.item_state in FAILED_ITEM_STATES


class BatchJob(BaseModel):
    """Batch manifest persisted as T-024 evidence."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["t024.batch.job.v1"] = BATCH_JOB_SCHEMA_VERSION
    batch_id: str
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=1, le=MAX_MVP_CHUNK_SIZE)
    items: list[BatchItem]
    state: BatchState = "CREATED"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("batch_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("batch_id must not be empty")
        return value

    @model_validator(mode="after")
    def validate_item_scopes(self) -> "BatchJob":
        job_ids = [item.job_id for item in self.items]
        idempotency_keys = [item.idempotency_key for item in self.items]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("batch item job_id values must be unique")
        if len(idempotency_keys) != len(set(idempotency_keys)):
            raise ValueError("batch item idempotency_key values must be unique")
        for item in self.items:
            if item.set_id and item.set_id in {self.batch_id, item.job_id, item.attempt_id}:
                raise ValueError("set_id must be distinct from batch_id, job_id, and attempt_id")
            if item.attempt_id and item.attempt_id in {self.batch_id, item.job_id, item.set_id}:
                raise ValueError("attempt_id must be distinct from batch_id, set_id, and job_id")
        return self


class ChunkPlan(BaseModel):
    """Sequential chunk execution plan. MVP concurrency remains 1."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.chunk.plan.v1"] = "t024.chunk.plan.v1"
    batch_id: str
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=1, le=MAX_MVP_CHUNK_SIZE)
    chunks: list[list[str]]
    concurrency: Literal[1] = 1


class ResumeDecision(BaseModel):
    """Evidence for idempotent resume behavior."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.resume.decision.v1"] = "t024.resume.decision.v1"
    batch_id: str
    reexecute_job_ids: list[str]
    skipped_completed_job_ids: list[str]
    duplicate_submission: bool = False


class BatchSummary(BaseModel):
    """Batch-level result without erasing per-item states."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.batch.summary.v1"] = "t024.batch.summary.v1"
    batch_id: str
    state: BatchState
    total_items: int
    completed_items: int
    failed_items: int
    item_results: list[dict[str, Any]]
    continue_remaining: bool


class PhotoSetItemEvidence(BaseModel):
    """Normalized photo evidence used to form and evaluate a set."""

    model_config = ConfigDict(extra="allow")

    job_id: str
    capture_group: str | None = None
    scene: str = "unknown"
    grouping_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    technical_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    quality_status: str = "APPROVED"
    source_limited: bool = False
    exposure: float = 0.0
    white_balance: float = 0.0
    color_cast: float = 0.0
    contrast: float = 0.0
    skin_tone: float = 0.0
    subject_emphasis: float = 0.0
    style_intent: float = 0.0
    user_set_id: str | None = None


class SetGrouping(BaseModel):
    """Traceable grouping decision for one set plus protected outliers."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.set.grouping.v1"] = "t024.set.grouping.v1"
    batch_id: str
    set_id: str
    grouped_job_ids: list[str]
    outlier_job_ids: list[str] = Field(default_factory=list)
    grouping_confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class RepresentativeSelection(BaseModel):
    """Deterministic representative image selection evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.representative.selection.v1"] = "t024.representative.selection.v1"
    batch_id: str
    set_id: str
    representative_job_id: str
    reasons: list[str] = Field(default_factory=list)


class SetBaseline(BaseModel):
    """Bounded relative consistency targets, never copied absolute settings."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.set.baseline.v1"] = "t024.set.baseline.v1"
    batch_id: str
    set_id: str
    exposure_target_range: tuple[float, float]
    wb_delta_range: tuple[float, float]
    color_cast_delta_range: tuple[float, float]
    contrast_delta_range: tuple[float, float]
    skin_tone_delta_range: tuple[float, float]
    subject_emphasis_delta_range: tuple[float, float]
    style_intent_delta_range: tuple[float, float]
    baseline_method: str = "bounded_relative_median"


class SetConsistencyItemResult(BaseModel):
    """Set-level score for one item; photo quality remains separate."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    consistency_score: float = Field(ge=0.0, le=100.0)
    outlier: bool = False
    outlier_reason: str | None = None
    individual_quality_status: str | None = None


class SetConsistencyResult(BaseModel):
    """T-024 set consistency result matching the harness schema."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["t024.set.consistency.v1"] = SET_CONSISTENCY_SCHEMA_VERSION
    batch_id: str
    set_id: str
    representative_job_id: str
    grouping_confidence: float = Field(ge=0.0, le=1.0)
    baseline: dict[str, Any]
    item_results: list[SetConsistencyItemResult]
    overall_score: float = Field(ge=0.0, le=100.0)


class BatchRuntimeEvidence(BaseModel):
    """Strict harness evidence envelope for a T-024 implementation run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t024.runtime.evidence.v1"] = RUNTIME_EVIDENCE_SCHEMA_VERSION
    ticket: Literal["T024"] = "T024"
    completed: bool
    regressions_passed: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)
