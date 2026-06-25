"""Schemas for T-027 plan routing and usage accounting."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PLAN_POLICY_SCHEMA_VERSION = "t027.plan.policy.v1"
USAGE_LEDGER_SCHEMA_VERSION = "t027.usage.ledger.v1"
RUNTIME_EVIDENCE_SCHEMA_VERSION = "t027.runtime.evidence.v1"

FORBIDDEN_T027_KEYS = {
    "intentionally_reduce_quality",
    "quality_multiplier",
    "silent_module_fallback",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class PlanPolicy(BaseModel):
    """Versioned plan policy controlled by the local policy registry."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: Literal["t027.plan.policy.v1"] = PLAN_POLICY_SCHEMA_VERSION
    plan_id: Literal["free", "lite", "standard", "pro"]
    version: int = Field(ge=1)
    status: Literal["ACTIVE", "INACTIVE"]
    analysis_provider: Literal["module", "model"]
    quality_provider: Literal["module", "model"]
    max_quality_retries: int = Field(ge=0, le=5)
    max_batch_size: int = Field(ge=1)
    max_input_megapixels: float = Field(ge=1)
    priority_class: Literal["low", "normal", "high"]
    monthly_photo_quota: int = Field(ge=0)
    fallback_policy: dict[str, Any] = Field(default_factory=dict)
    output_capabilities: list[str] = Field(default_factory=lambda: ["jpeg_srgb"])
    model_resource_budget: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        forbidden = find_forbidden_t027_keys(data)
        if forbidden:
            raise ValueError(f"T-027 plan policy contains forbidden quality/fallback fields: {forbidden}")
        return data

    @model_validator(mode="after")
    def validate_provider_mapping(self) -> "PlanPolicy":
        if self.plan_id in {"free", "lite"}:
            if self.analysis_provider != "module" or self.quality_provider != "module":
                raise ValueError("free/lite plans must use module providers")
            if self.fallback_policy.get("enabled"):
                raise ValueError("free/lite plans must not enable model fallback policy")
        if self.plan_id in {"standard", "pro"}:
            if self.analysis_provider != "model" or self.quality_provider != "model":
                raise ValueError("standard/pro plans must use model providers")
        return self

    @property
    def policy_hash(self) -> str:
        return stable_sha256(self.model_dump(mode="json"))


class PlanPolicySnapshot(BaseModel):
    """Immutable policy snapshot attached to a job at route time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t027.plan.snapshot.v1"] = "t027.plan.snapshot.v1"
    snapshot_id: str
    user_scope_id: str
    job_id: str
    captured_at: str
    plan: PlanPolicy
    policy_hash: str

    @field_validator("user_scope_id", "job_id")
    @classmethod
    def non_empty_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity fields must not be empty")
        return value

    @model_validator(mode="after")
    def validate_policy_hash(self) -> "PlanPolicySnapshot":
        if self.policy_hash != self.plan.policy_hash:
            raise ValueError("policy snapshot hash does not match plan payload")
        return self


class PlanRouteDecision(BaseModel):
    """Machine-readable route decision for a job."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t027.plan.route.decision.v1"] = "t027.plan.route.decision.v1"
    decision: Literal["ALLOW", "DENY"]
    reason: str
    user_scope_id: str
    job_id: str
    requested_plan_id: str
    snapshot: PlanPolicySnapshot | None = None
    requested_analysis_provider: Literal["module", "model"] | None = None
    executed_analysis_provider: Literal["module", "model"] | None = None
    requested_quality_provider: Literal["module", "model"] | None = None
    executed_quality_provider: Literal["module", "model"] | None = None
    model_initialization_allowed: bool = False
    fallback_used: bool = False
    audit: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_allow_has_snapshot(self) -> "PlanRouteDecision":
        if self.decision == "ALLOW" and self.snapshot is None:
            raise ValueError("ALLOW route decisions require a policy snapshot")
        return self


class UsageLedgerEvent(BaseModel):
    """Idempotent usage ledger event matching the T-027 harness schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t027.usage.ledger.v1"] = USAGE_LEDGER_SCHEMA_VERSION
    usage_event_id: str
    idempotency_key: str
    user_scope_id: str
    job_id: str
    plan_id: str
    plan_version: int
    state: Literal["RESERVED", "COMMITTED", "RELEASED"]
    photo_units: int = Field(ge=0)
    compute_metrics: dict[str, Any] = Field(default_factory=dict)
    reason: str

    @field_validator("usage_event_id", "idempotency_key", "user_scope_id", "job_id", "plan_id", "reason")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ledger event text fields must not be empty")
        return value


class UsageTotals(BaseModel):
    """User-scoped reconciled usage totals."""

    model_config = ConfigDict(extra="forbid")

    user_scope_id: str
    reserved_photo_units: int = 0
    committed_photo_units: int = 0
    released_photo_units: int = 0
    compute_metrics: dict[str, float] = Field(default_factory=dict)

    @property
    def active_photo_units(self) -> int:
        return self.reserved_photo_units + self.committed_photo_units


class T027RuntimeEvidence(BaseModel):
    """Strict harness evidence envelope for a T-027 implementation run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t027.runtime.evidence.v1"] = RUNTIME_EVIDENCE_SCHEMA_VERSION
    ticket: Literal["T027"] = "T027"
    completed: bool
    regressions_passed: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)


def find_forbidden_t027_keys(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_T027_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_t027_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_t027_keys(child, f"{prefix}[{index}]"))
    return found
