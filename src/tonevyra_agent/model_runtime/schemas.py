"""T-022 runtime envelope schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelRuntimeEnvelope(BaseModel):
    """Persistable evidence for one local model call."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t022.model.runtime.envelope.v1"] = "t022.model.runtime.envelope.v1"
    request_id: str
    job_id: str
    attempt_id: str
    operation: Literal["analysis", "quality"]
    provider_type: Literal["model"] = "model"
    model_id: str
    model_revision: str
    model_checksum: str
    runtime_backend: str
    runtime_version: str
    device: str
    dtype: str
    quantization: str
    started_at: str
    completed_at: str
    latency_ms: int = Field(ge=0)
    parse_status: Literal["SUCCESS", "FAILED"]
    confidence: float = Field(ge=0.0, le=1.0)
    raw_output_checksum: str
    normalized_output: dict[str, Any]
    source_checksum: str | None = None
    export_checksum: str | None = None
    model_runtime_retry_count: int = Field(default=0, ge=0)
    quality_retry_count: int = Field(default=0, ge=0)

    @field_validator("request_id", "job_id", "attempt_id", "model_id", "model_revision", "runtime_backend")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("model_checksum", "raw_output_checksum")
    @classmethod
    def checksum_prefix(cls, value: str) -> str:
        if not value.startswith("sha256:"):
            raise ValueError("checksum fields must use sha256:<hex>")
        return value
