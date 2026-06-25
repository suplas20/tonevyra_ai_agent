"""Schemas for T-026 benchmark datasets, runs, and release gates."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BENCHMARK_CASE_SCHEMA_VERSION = "t026.benchmark.case.v1"
BENCHMARK_RUN_SCHEMA_VERSION = "t026.benchmark.run.v1"
RUNTIME_EVIDENCE_SCHEMA_VERSION = "t026.runtime.evidence.v1"

FORBIDDEN_T026_KEYS = {
    "silent_threshold_relaxation",
    "provider_labels_visible",
    "test_used_for_training",
}


class BenchmarkCase(BaseModel):
    """One versioned benchmark dataset case."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["t026.benchmark.case.v1"] = BENCHMARK_CASE_SCHEMA_VERSION
    dataset_id: str
    dataset_version: str
    split: Literal["train", "calibration", "test"]
    case_id: str
    source_checksum: str
    reference_checksums: list[str] = Field(min_length=1)
    license_or_consent: str
    scene_class: str
    difficulty: Literal["simple", "moderate", "complex"]
    required_metrics: list[str] = Field(min_length=1)

    @field_validator(
        "dataset_id",
        "dataset_version",
        "case_id",
        "source_checksum",
        "license_or_consent",
        "scene_class",
    )
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_checksum")
    @classmethod
    def checksum_must_be_declared(cls, value: str) -> str:
        if not value.startswith("sha256:"):
            raise ValueError("source_checksum must use sha256: prefix")
        return value

    @field_validator("reference_checksums")
    @classmethod
    def reference_checksums_must_be_declared(cls, value: list[str]) -> list[str]:
        for checksum in value:
            if not isinstance(checksum, str) or not checksum.startswith("sha256:"):
                raise ValueError("reference_checksums must use sha256: prefix")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class BenchmarkConditions(BaseModel):
    """Comparable runtime/export conditions for A-B runs."""

    model_config = ConfigDict(extra="forbid")

    source_case_ids: list[str]
    export_settings_hash: str
    lightroom_version: str
    plugin_version: str
    quality_metric_version: str
    benchmark_policy_version: str


class HumanBlindReview(BaseModel):
    """Human review evidence kept separate from automated metrics."""

    model_config = ConfigDict(extra="allow")

    review_session_id: str
    blind_pair_id: str
    randomized_order: bool
    provider_labels_hidden: bool
    criteria_scores: dict[str, float] = Field(default_factory=dict)
    preference: str
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_blind_review(self) -> "HumanBlindReview":
        if not self.randomized_order:
            raise ValueError("human review order must be randomized")
        if not self.provider_labels_hidden:
            raise ValueError("provider labels must be hidden")
        return self

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class RegressionThresholds(BaseModel):
    """Versioned release gate thresholds."""

    model_config = ConfigDict(extra="allow")

    version: str
    critical: dict[str, float]
    genre: dict[str, float] = Field(default_factory=dict)
    silent_relaxation_allowed: Literal[False] = False

    @field_validator("version")
    @classmethod
    def non_empty_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("threshold version must not be empty")
        return value


class RegressionDecision(BaseModel):
    """Machine-readable release gate result."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t026.regression.decision.v1"] = "t026.regression.decision.v1"
    decision: Literal["PASS", "FAIL"]
    threshold_version: str
    blocking_reasons: list[str] = Field(default_factory=list)
    checked_metrics: dict[str, float] = Field(default_factory=dict)


class BenchmarkRunResult(BaseModel):
    """Benchmark run result matching the T-026 harness schema."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["t026.benchmark.run.v1"] = BENCHMARK_RUN_SCHEMA_VERSION
    run_id: str
    dataset_id: str
    dataset_version: str
    candidate_version: str
    baseline_version: str
    conditions_hash: str
    aggregate_metrics: dict[str, Any]
    genre_metrics: dict[str, Any]
    regression_decision: Literal["PASS", "FAIL"]

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class QualityClaim(BaseModel):
    """A quality claim must be backed by dataset, run, and expert review evidence."""

    model_config = ConfigDict(extra="allow")

    claim: str
    dataset_id: str | None
    run_id: str | None
    expert_review_id: str | None

    def is_substantiated(self) -> bool:
        return bool(self.dataset_id and self.run_id and self.expert_review_id)


class T026RuntimeEvidence(BaseModel):
    """Strict harness evidence envelope for a T-026 implementation run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t026.runtime.evidence.v1"] = RUNTIME_EVIDENCE_SCHEMA_VERSION
    ticket: Literal["T026"] = "T026"
    completed: bool
    regressions_passed: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)


def find_forbidden_t026_keys(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_T026_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_t026_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_t026_keys(child, f"{prefix}[{index}]"))
    return found


def _raise_forbidden(value: Any) -> None:
    forbidden = find_forbidden_t026_keys(value)
    if forbidden:
        raise ValueError(f"T-026 benchmark payload contains forbidden fields: {forbidden}")
