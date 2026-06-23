"""T-023 semantic region and local adjustment schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SEMANTIC_SCHEMA_VERSION = "t023.semantic.analysis.v1"
LOCAL_PLAN_SCHEMA_VERSION = "t023.local.adjustment.plan.v1"
RUNTIME_EVIDENCE_SCHEMA_VERSION = "t023.runtime.evidence.v1"
MASK_CAPABILITY_SCHEMA_VERSION = "t023.mask.capability.snapshot.v1"
CONFLICT_RESOLUTION_SCHEMA_VERSION = "t023.conflict.resolution.v1"

FORBIDDEN_T023_KEYS = {
    "lightroom_mask_payload",
    "plugin_command",
    "final_develop_settings",
    "force_state_transition",
    "preset_path",
    "execute_mask",
}

RegionType = Literal[
    "primary_subject",
    "secondary_subject",
    "person",
    "face",
    "skin",
    "hair",
    "sky",
    "background",
    "foreground",
    "product",
    "object",
]

ProviderType = Literal["module", "model"]
SupportedMaskType = Literal["subject", "people", "face_skin", "sky", "background", "linear_gradient", "radial_gradient"]
FallbackBehavior = Literal["skip", "global_only", "technical_failure"]

LOCAL_ADJUSTMENT_BOUNDS: dict[str, tuple[float, float]] = {
    "exposure_delta": (-0.7, 0.7),
    "highlights_delta": (-0.5, 0.5),
    "shadows_delta": (-0.5, 0.5),
    "contrast_delta": (-0.35, 0.35),
    "clarity_delta": (-0.3, 0.3),
    "texture_delta": (-0.3, 0.3),
    "saturation_delta": (-0.3, 0.3),
    "temperature_delta": (-800.0, 800.0),
    "tint_delta": (-25.0, 25.0),
    "noise_reduction_delta": (0.0, 35.0),
    "sharpening_delta": (-20.0, 25.0),
}


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class SemanticRegion(BaseModel):
    """Normalized non-executable evidence for one semantic region."""

    model_config = ConfigDict(extra="forbid")

    region_id: str
    region_type: RegionType
    priority: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    quality_risks: list[Any] = Field(default_factory=list)
    recommended_intents: list[str] = Field(default_factory=list)
    source: str

    @field_validator("region_id", "source")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class SemanticAnalysis(BaseModel):
    """Versioned semantic analysis consumed by the local adjustment planner."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["t023.semantic.analysis.v1"] = SEMANTIC_SCHEMA_VERSION
    job_id: str
    attempt_id: str
    provider_type: ProviderType
    primary_region_id: str | None = None
    created_at: str = Field(default_factory=utc_now)
    regions: list[SemanticRegion] = Field(default_factory=list)

    @field_validator("job_id", "attempt_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data

    @model_validator(mode="after")
    def validate_primary_region(self) -> "SemanticAnalysis":
        region_ids = {region.region_id for region in self.regions}
        if self.primary_region_id is not None and self.primary_region_id not in region_ids:
            raise ValueError("primary_region_id must reference a semantic region")
        if self.regions and self.primary_region_id is None:
            raise ValueError("primary_region_id is required when regions are present")
        return self


class MaskCapabilitySnapshot(BaseModel):
    """Supported Lightroom local adjustment capability evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t023.mask.capability.snapshot.v1"] = MASK_CAPABILITY_SCHEMA_VERSION
    capability_snapshot_id: str
    supported_mask_types: list[SupportedMaskType]
    plugin_version: str = "unknown"
    created_at: str = Field(default_factory=utc_now)
    degraded_mode: bool = False
    degraded_reason: str | None = None

    @field_validator("capability_snapshot_id")
    @classmethod
    def non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("capability_snapshot_id must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class LocalAdjustmentItem(BaseModel):
    """One bounded local adjustment plan entry."""

    model_config = ConfigDict(extra="forbid")

    mask_plan_id: str
    region_id: str
    supported_mask_type: SupportedMaskType
    bounded_adjustment_intents: dict[str, float] = Field(default_factory=dict)
    conflict_resolution: list[str] = Field(default_factory=list)
    fallback_behavior: FallbackBehavior

    @field_validator("mask_plan_id", "region_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("bounded_adjustment_intents")
    @classmethod
    def validate_bounded_intents(cls, value: dict[str, float]) -> dict[str, float]:
        for key, raw_delta in value.items():
            if key not in LOCAL_ADJUSTMENT_BOUNDS:
                raise ValueError(f"unsupported local adjustment intent: {key}")
            low, high = LOCAL_ADJUSTMENT_BOUNDS[key]
            delta = float(raw_delta)
            if delta < low or delta > high:
                raise ValueError(f"{key} must be between {low} and {high}")
            value[key] = delta
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class LocalAdjustmentPlan(BaseModel):
    """Planner-owned local adjustment plan. Provider outputs must not create this."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t023.local.adjustment.plan.v1"] = LOCAL_PLAN_SCHEMA_VERSION
    job_id: str
    attempt_id: str
    planner_version: str
    capability_snapshot_id: str
    degraded_mode: bool
    plans: list[LocalAdjustmentItem] = Field(default_factory=list)

    @field_validator("job_id", "attempt_id", "planner_version", "capability_snapshot_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data

    def validate_region_references(self, semantic_analysis: SemanticAnalysis) -> None:
        region_ids = {region.region_id for region in semantic_analysis.regions}
        unknown = sorted({plan.region_id for plan in self.plans} - region_ids)
        if unknown:
            raise ValueError(f"local plan references unknown semantic regions: {unknown}")


class ConflictResolutionEvidence(BaseModel):
    """Deterministic global/local conflict resolution evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t023.conflict.resolution.v1"] = CONFLICT_RESOLUTION_SCHEMA_VERSION
    job_id: str
    attempt_id: str
    planner_version: str
    decisions: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class T023RuntimeEvidence(BaseModel):
    """Strict harness evidence envelope for an implementation run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t023.runtime.evidence.v1"] = RUNTIME_EVIDENCE_SCHEMA_VERSION
    ticket: Literal["T023"] = "T023"
    completed: bool
    regressions_passed: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


def clamp_local_adjustments(values: dict[str, float]) -> dict[str, float]:
    """Clamp known local adjustment deltas to T-023 safety limits."""

    clamped: dict[str, float] = {}
    for key, raw_delta in values.items():
        if key not in LOCAL_ADJUSTMENT_BOUNDS:
            raise ValueError(f"unsupported local adjustment intent: {key}")
        low, high = LOCAL_ADJUSTMENT_BOUNDS[key]
        delta = min(max(float(raw_delta), low), high)
        clamped[key] = round(delta, 4)
    return clamped


def find_forbidden_t023_keys(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_T023_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_t023_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_t023_keys(child, f"{prefix}[{index}]"))
    return found


def _raise_forbidden(value: Any) -> None:
    forbidden = find_forbidden_t023_keys(value)
    if forbidden:
        raise ValueError(f"T-023 provider/planner payload contains forbidden execution fields: {forbidden}")
