"""Schemas for the file-based Lightroom JSON bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tonevyra_agent.core.enums import ErrorCode


LIGHTROOM_COMMAND_PING = "PING"
LIGHTROOM_COMMAND_APPLY_ADJUSTMENTS_AND_EXPORT = "APPLY_ADJUSTMENTS_AND_EXPORT"
LIGHTROOM_COMMAND_APPLY_SETTINGS = "APPLY_LIGHTROOM_SETTINGS"
LIGHTROOM_COMMAND_EXPORT_CORRECTED_IMAGE = "EXPORT_CORRECTED_IMAGE"
LIGHTROOM_COMMAND_APPLY_MASK_PLAN = "APPLY_LIGHTROOM_MASK_PLAN"
LIGHTROOM_RESPONSE_SUCCESS = "success"
LIGHTROOM_RESPONSE_FAILED = "failed"
LIGHTROOM_APPLY_REQUEST_SCHEMA = "t019.lightroom_apply.request.v1"
LIGHTROOM_APPLY_RESULT_SCHEMA = "t019.lightroom_apply.result.v1"
LIGHTROOM_EXPORT_REQUEST_SCHEMA = "t020.lightroom_export.request.v1"
LIGHTROOM_EXPORT_RESULT_SCHEMA = "t020.lightroom_export.result.v1"
LIGHTROOM_MASK_REQUEST_SCHEMA = "t029.mask_apply.request.v1"
LIGHTROOM_MASK_PLAN_SCHEMA = "t029.mask_plan.v1"
LIGHTROOM_MASK_RESULT_SCHEMA = "t029.mask_apply.result.v1"

LIGHTROOM_APPLY_ALLOWED_SETTINGS = {
    "exposure",
    "contrast",
    "highlights",
    "shadows",
    "whites",
    "blacks",
    "temp",
    "temperature_delta",
    "tint",
    "vibrance",
    "saturation",
    "texture",
    "clarity",
    "dehaze",
    "sharpening",
    "noise_reduction",
    "red_saturation",
    "orange_saturation",
    "yellow_saturation",
    "green_saturation",
    "aqua_saturation",
    "blue_saturation",
    "purple_saturation",
    "magenta_saturation",
    "red_hue",
    "orange_hue",
    "yellow_hue",
    "green_hue",
    "aqua_hue",
    "blue_hue",
    "purple_hue",
    "magenta_hue",
    "red_luminance",
    "orange_luminance",
    "yellow_luminance",
    "green_luminance",
    "aqua_luminance",
    "blue_luminance",
    "purple_luminance",
    "magenta_luminance",
}

LIGHTROOM_MASK_ALLOWED_ADJUSTMENTS = {
    "Exposure2012": (-1.0, 1.0),
    "Shadows2012": (-40.0, 40.0),
    "Temperature": (-20.0, 20.0),
    "Tint": (-20.0, 20.0),
    "Saturation": (-35.0, 35.0),
    "Vibrance": (-30.0, 30.0),
    "Texture": (-20.0, 20.0),
    "Clarity2012": (-20.0, 20.0),
    "Dehaze": (-15.0, 15.0),
}

LIGHTROOM_NATIVE_MASK_TYPES = {"subject", "people", "object", "sky", "background"}


class LightroomExportSettings(BaseModel):
    """Export settings understood by the fake worker and future Lua plugin."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["JPEG"] = "JPEG"
    quality: int = Field(default=92, ge=1, le=100)


class LightroomRequestPayload(BaseModel):
    """Request payload written by Python for Lightroom-facing processing."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    request_id: str
    task_id: str
    command: Literal["PING", "APPLY_ADJUSTMENTS_AND_EXPORT"] = LIGHTROOM_COMMAND_APPLY_ADJUSTMENTS_AND_EXPORT
    source_path: str | None = None
    export_path: str | None = None
    correction_plan_path: str | None = None
    adjustments: dict[str, float] = Field(default_factory=dict)
    export: LightroomExportSettings = Field(default_factory=LightroomExportSettings)

    @field_validator("request_id", "task_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_path", "export_path", "correction_plan_path")
    @classmethod
    def normalized_absolute_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("path must be absolute")
        return str(path.resolve())

    @model_validator(mode="after")
    def validate_command_fields(self) -> "LightroomRequestPayload":
        if self.command == LIGHTROOM_COMMAND_PING:
            return self
        missing = [
            field_name
            for field_name in ("source_path", "export_path", "correction_plan_path")
            if getattr(self, field_name) is None
        ]
        if missing:
            raise ValueError(f"{self.command} request requires: {', '.join(missing)}")
        return self


class LightroomResponsePayload(BaseModel):
    """Response payload returned by the fake worker or future Lua plugin."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    request_id: str
    task_id: str
    command: Literal["PING", "APPLY_ADJUSTMENTS_AND_EXPORT"] | None = None
    status: Literal["success", "failed"]
    export_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @field_validator("request_id", "task_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("export_path")
    @classmethod
    def normalized_export_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("export_path must be absolute")
        return str(path.resolve())

    @field_validator("error_code")
    @classmethod
    def known_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ErrorCode(value).value

    @model_validator(mode="after")
    def validate_status_fields(self) -> "LightroomResponsePayload":
        if (
            self.status == LIGHTROOM_RESPONSE_SUCCESS
            and self.command != LIGHTROOM_COMMAND_PING
            and self.export_path is None
        ):
            raise ValueError("success response requires export_path")
        if self.status == LIGHTROOM_RESPONSE_FAILED and self.error_code is None:
            raise ValueError("failed response requires error_code")
        return self


class LightroomApplyRequestPayload(BaseModel):
    """T-019 folder-driven request written by Python for the real Lightroom plugin."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t019.lightroom_apply.request.v1"] = LIGHTROOM_APPLY_REQUEST_SCHEMA
    request_id: str
    request_origin: Literal["tonevyra_agent"] = "tonevyra_agent"
    command: Literal["APPLY_LIGHTROOM_SETTINGS"] = LIGHTROOM_COMMAND_APPLY_SETTINGS
    operation: Literal["apply_develop_settings"] = "apply_develop_settings"
    task_id: str
    source_path: str
    correction_plan_id: str | None = None
    created_at: str
    develop_settings: dict[str, float]
    local_adjustments: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=lambda: {"non_destructive_required": True})
    runtime_context: dict[str, str] = Field(default_factory=dict)

    @field_validator("request_id", "task_id", "created_at")
    @classmethod
    def non_empty_apply_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_path")
    @classmethod
    def absolute_source_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("source_path must be absolute")
        return str(path.resolve())

    @field_validator("develop_settings")
    @classmethod
    def supported_develop_settings(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("develop_settings must not be empty")
        unsupported = set(value) - LIGHTROOM_APPLY_ALLOWED_SETTINGS
        if unsupported:
            raise ValueError(f"unsupported develop setting: {sorted(unsupported)}")
        return value

    @model_validator(mode="after")
    def validate_safety(self) -> "LightroomApplyRequestPayload":
        if self.safety.get("non_destructive_required") is not True:
            raise ValueError("safety.non_destructive_required must be true")
        return self


class LightroomApplyResultPayload(BaseModel):
    """T-019 Lightroom apply-adapter result written by the Lightroom plugin."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = LIGHTROOM_APPLY_RESULT_SCHEMA
    request_id: str
    request_origin: Literal["lightroom_plugin"] = "lightroom_plugin"
    command: Literal["APPLY_LIGHTROOM_SETTINGS"] = LIGHTROOM_COMMAND_APPLY_SETTINGS
    task_id: str
    status: Literal["applied", "partial", "failed", "skipped"]
    source_path: str
    catalog_action: Literal["found_existing", "imported", "not_imported", "unknown"] = "unknown"
    applied_parameters: dict[str, float] = Field(default_factory=dict)
    skipped_parameters: dict[str, Any] = Field(default_factory=dict)
    applied_settings: dict[str, float] = Field(default_factory=dict)
    skipped_settings: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    message: str = ""
    completed_at: str | None = None
    lightroom_result: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    write_access_retry_count: int | None = None
    write_access_wait_ms: int | None = None

    @field_validator("request_id", "task_id")
    @classmethod
    def non_empty_result_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_path")
    @classmethod
    def absolute_result_source_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("source_path must be absolute")
        return str(path.resolve())

    @model_validator(mode="after")
    def validate_result_fields(self) -> "LightroomApplyResultPayload":
        if self.schema_version not in {LIGHTROOM_APPLY_RESULT_SCHEMA, "1.0"}:
            raise ValueError("unsupported Lightroom apply result schema_version")
        if not self.applied_settings and self.applied_parameters:
            self.applied_settings = dict(self.applied_parameters)
        if not self.applied_parameters and self.applied_settings:
            self.applied_parameters = dict(self.applied_settings)
        if not self.skipped_settings and self.skipped_parameters:
            self.skipped_settings = dict(self.skipped_parameters)
        if not self.skipped_parameters and self.skipped_settings:
            self.skipped_parameters = dict(self.skipped_settings)
        if self.status == "failed" and self.error is None and self.error_code:
            self.error = {
                "code": self.error_code,
                "message": self.message,
                "recoverable": True,
            }
        if "worker_running" not in self.lightroom_result:
            raise ValueError("lightroom_result.worker_running is required")
        if self.status in {"applied", "partial"}:
            if self.lightroom_result.get("develop_settings_applied") is not True:
                raise ValueError("successful apply result requires develop_settings_applied=true")
            if not self.applied_settings:
                raise ValueError("successful apply result requires applied_settings")
        if self.status == "failed":
            if not isinstance(self.error, dict):
                raise ValueError("failed apply result requires error")
            for field_name in ("code", "message", "recoverable"):
                if field_name not in self.error:
                    raise ValueError(f"failed apply result requires error.{field_name}")
        return self


class LightroomOutputSharpening(BaseModel):
    """MVP Lightroom export output-sharpening settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    medium: Literal["screen"] = "screen"
    amount: Literal["standard"] = "standard"


class LightroomFinalExportSettings(BaseModel):
    """T-020 corrected-rendition export settings."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["JPEG"] = "JPEG"
    quality: int = Field(default=95, ge=1, le=100)
    color_space: Literal["sRGB"] = "sRGB"
    resize: Literal[False] = False
    output_sharpening: LightroomOutputSharpening = Field(default_factory=LightroomOutputSharpening)
    metadata_policy: Literal["copyright_and_capture_only"] = "copyright_and_capture_only"
    overwrite: Literal[False] = False


class LightroomExportRequestPayload(BaseModel):
    """T-020 request written by Python for the Lightroom final export adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t020.lightroom_export.request.v1"] = LIGHTROOM_EXPORT_REQUEST_SCHEMA
    request_id: str
    task_id: str
    apply_request_id: str
    source_path: str
    export_path: str
    command: Literal["EXPORT_CORRECTED_IMAGE"] = LIGHTROOM_COMMAND_EXPORT_CORRECTED_IMAGE
    export_settings: LightroomFinalExportSettings = Field(default_factory=LightroomFinalExportSettings)
    created_at: str

    @field_validator("request_id", "task_id", "apply_request_id", "created_at")
    @classmethod
    def non_empty_export_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_path", "export_path")
    @classmethod
    def absolute_export_paths(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("path must be absolute")
        return str(path.resolve())

    @model_validator(mode="after")
    def validate_export_paths(self) -> "LightroomExportRequestPayload":
        if Path(self.source_path) == Path(self.export_path):
            raise ValueError("export_path must not equal source_path")
        return self


class LightroomExportResultPayload(BaseModel):
    """T-020 result written by the Lightroom final export adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t020.lightroom_export.result.v1"] = LIGHTROOM_EXPORT_RESULT_SCHEMA
    request_id: str
    task_id: str
    apply_request_id: str
    source_path: str
    export_path: str
    status: Literal["exported", "failed"]
    export_settings: dict[str, Any]
    lightroom_result: dict[str, Any]
    file_result: dict[str, Any]
    error_code: str | None = None
    message: str = ""
    completed_at: str
    recoverable: bool | None = None

    @field_validator("request_id", "task_id", "apply_request_id", "completed_at")
    @classmethod
    def non_empty_export_result_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_path", "export_path")
    @classmethod
    def absolute_export_result_paths(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("path must be absolute")
        return str(path.resolve())

    @field_validator("error_code")
    @classmethod
    def known_export_error_code(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        return ErrorCode(value).value

    @model_validator(mode="after")
    def validate_export_result(self) -> "LightroomExportResultPayload":
        if Path(self.source_path) == Path(self.export_path):
            raise ValueError("export_path must not equal source_path")
        if self.status == "exported":
            required_lr = (
                "plugin_loaded",
                "worker_running",
                "source_photo_found",
                "export_started",
                "export_completed",
            )
            for field_name in required_lr:
                if self.lightroom_result.get(field_name) is not True:
                    raise ValueError(f"exported result requires lightroom_result.{field_name}=true")
            if self.file_result.get("exists") is not True:
                raise ValueError("exported result requires file_result.exists=true")
            size = self.file_result.get("size_bytes")
            if not isinstance(size, int) or size <= 0:
                raise ValueError("exported result requires file_result.size_bytes > 0")
            if self.error_code is not None:
                raise ValueError("exported result must not contain error_code")
        if self.status == "failed" and self.error_code is None:
            raise ValueError("failed export result requires error_code")
        return self


class LightroomMaskGeometry(BaseModel):
    """T-029 normalized predicted target geometry."""

    model_config = ConfigDict(extra="forbid")

    coordinate_space: Literal["oriented_normalized_image"] = "oriented_normalized_image"
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    rotation_deg: float = Field(ge=-180.0, le=180.0)


class LightroomMaskNativeAssessment(BaseModel):
    """Planner-owned native AI mask detection evidence."""

    model_config = ConfigDict(extra="forbid")

    attempted_types: list[Literal["subject", "people", "object", "sky", "background"]]
    target_detected: bool
    reason_code: str

    @field_validator("attempted_types")
    @classmethod
    def non_empty_unique_types(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("attempted_types must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("attempted_types must be unique")
        return value

    @field_validator("reason_code")
    @classmethod
    def non_empty_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason_code must not be empty")
        return value


class LightroomMaskPointColor(BaseModel):
    """Optional local point-color intent. The current plugin may report it unsupported."""

    model_config = ConfigDict(extra="forbid")

    source_hue: float = Field(ge=0.0, le=360.0)
    source_saturation: float = Field(ge=0.0, le=1.0)
    source_luminance: float = Field(ge=0.0, le=1.0)
    hue_shift: float = Field(ge=-60.0, le=60.0)
    saturation_shift: float = Field(ge=-0.5, le=0.5)
    luminance_shift: float = Field(ge=-0.3, le=0.3)


class LightroomMaskSafety(BaseModel):
    """Safety invariants for native mask execution."""

    model_config = ConfigDict(extra="forbid")

    preserve_user_masks: Literal[True] = True
    non_destructive_required: Literal[True] = True
    max_background_spill: float = Field(ge=0.0, le=1.0)


class LightroomMaskOperation(BaseModel):
    """One T-029 local adjustment operation.

    Radial/template fallback fields are intentionally absent and rejected by
    extra="forbid"; native execution is allowed only with target_detected=true.
    """

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    target_region_id: str
    strategy: Literal["native_ai", "skip_local", "review_required"]
    native_assessment: LightroomMaskNativeAssessment
    predicted_geometry: LightroomMaskGeometry
    mask_name: str
    local_adjustments: dict[str, float]
    point_color: LightroomMaskPointColor | None = None
    safety: LightroomMaskSafety

    @field_validator("operation_id", "target_region_id", "mask_name")
    @classmethod
    def non_empty_operation_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("mask_name")
    @classmethod
    def tonevyra_mask_name(cls, value: str) -> str:
        if not value.startswith("Tonevyra::T029::"):
            raise ValueError("mask_name must start with Tonevyra::T029::")
        return value

    @field_validator("local_adjustments")
    @classmethod
    def bounded_local_adjustments(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("local_adjustments must not be empty")
        unknown = set(value) - set(LIGHTROOM_MASK_ALLOWED_ADJUSTMENTS)
        if unknown:
            raise ValueError(f"unsupported local adjustment: {sorted(unknown)}")
        for key, raw in value.items():
            number = float(raw)
            low, high = LIGHTROOM_MASK_ALLOWED_ADJUSTMENTS[key]
            if number < low or number > high:
                raise ValueError(f"{key} must be between {low} and {high}")
            value[key] = number
        return value

    @model_validator(mode="after")
    def validate_native_strategy(self) -> "LightroomMaskOperation":
        detected = self.native_assessment.target_detected
        if self.strategy == "native_ai" and detected is not True:
            raise ValueError("native_ai strategy requires native_assessment.target_detected=true")
        if self.strategy in {"skip_local", "review_required"} and detected is not False:
            raise ValueError(f"{self.strategy} strategy requires native_assessment.target_detected=false")
        return self


class LightroomMaskPlan(BaseModel):
    """T-029 planner-owned native mask plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t029.mask_plan.v1"] = LIGHTROOM_MASK_PLAN_SCHEMA
    plan_id: str
    planner_version: str
    operations: list[LightroomMaskOperation]

    @field_validator("plan_id", "planner_version")
    @classmethod
    def non_empty_plan_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("operations")
    @classmethod
    def non_empty_operations(cls, value: list[LightroomMaskOperation]) -> list[LightroomMaskOperation]:
        if not value:
            raise ValueError("operations must not be empty")
        return value


class LightroomMaskApplyRequestPayload(BaseModel):
    """T-029 native Lightroom mask request written by Python for the plugin."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t029.mask_apply.request.v1"] = LIGHTROOM_MASK_REQUEST_SCHEMA
    request_id: str
    task_id: str
    job_id: str
    attempt_id: str
    source_path: str
    command: Literal["APPLY_LIGHTROOM_MASK_PLAN"] = LIGHTROOM_COMMAND_APPLY_MASK_PLAN
    idempotency_key: str = Field(min_length=8)
    capability_snapshot_id: str
    mask_plan: LightroomMaskPlan
    created_at: str

    @field_validator("request_id", "task_id", "job_id", "attempt_id", "capability_snapshot_id", "created_at")
    @classmethod
    def non_empty_mask_request_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("source_path")
    @classmethod
    def absolute_mask_source_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("source_path must be absolute")
        return str(path.resolve())


class LightroomMaskCapabilitySnapshot(BaseModel):
    """Plugin-reported native mask capability evidence."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    lightroom_version: str
    plugin_version: str
    mask_plan_command_supported: bool
    native_mask_command_supported: bool
    native_ai_mask_types: list[str] = Field(default_factory=list)
    local_point_color_supported: bool
    mask_result_introspection_level: str = ""
    rollback_supported: bool

    @field_validator("snapshot_id", "lightroom_version", "plugin_version")
    @classmethod
    def non_empty_capability_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("native_ai_mask_types", mode="before")
    @classmethod
    def normalize_lua_empty_mask_types(cls, value: Any) -> Any:
        if value == {}:
            return []
        return value

    @field_validator("native_ai_mask_types")
    @classmethod
    def known_unique_native_mask_types(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("native_ai_mask_types must be unique")
        unknown = set(value) - LIGHTROOM_NATIVE_MASK_TYPES
        if unknown:
            raise ValueError(f"unsupported native_ai_mask_types: {sorted(unknown)}")
        return value


class LightroomMaskOperationResult(BaseModel):
    """Per-operation T-029 plugin result."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    status: Literal["applied", "reused", "skipped", "failed"]
    strategy: Literal["native_ai", "skip_local", "review_required"]
    mask_name: str
    mask_created_or_reused: Literal["created", "reused", "not_created"]
    applied_adjustments: dict[str, float] = Field(default_factory=dict)
    point_color_status: Literal["applied", "unsupported", "skipped", "failed"]
    warnings: list[str] = Field(default_factory=list)

    @field_validator("operation_id", "mask_name")
    @classmethod
    def non_empty_operation_result_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("mask_name")
    @classmethod
    def tonevyra_result_mask_name(cls, value: str) -> str:
        if not value.startswith("Tonevyra::T029::"):
            raise ValueError("mask_name must start with Tonevyra::T029::")
        return value

    @model_validator(mode="after")
    def validate_mask_creation_state(self) -> "LightroomMaskOperationResult":
        if self.status in {"applied", "reused"}:
            if self.strategy != "native_ai":
                raise ValueError("applied/reused mask operation requires strategy=native_ai")
            if self.mask_created_or_reused == "not_created":
                raise ValueError("applied/reused mask operation requires created or reused mask evidence")
            if not self.applied_adjustments:
                raise ValueError("applied/reused mask operation requires applied_adjustments")
        if self.status in {"skipped", "failed"} and self.mask_created_or_reused != "not_created":
            raise ValueError("skipped/failed mask operation must not claim mask creation")
        return self


class LightroomMaskApplyResultPayload(BaseModel):
    """T-029 native Lightroom mask result written by the plugin."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t029.mask_apply.result.v1"] = LIGHTROOM_MASK_RESULT_SCHEMA
    request_id: str
    task_id: str
    job_id: str
    attempt_id: str
    status: Literal["applied", "partial", "skipped", "failed"]
    idempotency_key: str = Field(min_length=8)
    capability_snapshot: LightroomMaskCapabilitySnapshot
    operation_results: list[LightroomMaskOperationResult]
    pre_apply_snapshot_ref: str
    post_apply_snapshot_ref: str
    rollback_performed: bool
    error_code: str | None = None
    message: str | None = None
    completed_at: str

    @field_validator(
        "request_id",
        "task_id",
        "job_id",
        "attempt_id",
        "pre_apply_snapshot_ref",
        "post_apply_snapshot_ref",
        "completed_at",
    )
    @classmethod
    def non_empty_mask_result_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("operation_results")
    @classmethod
    def non_empty_operation_results(cls, value: list[LightroomMaskOperationResult]) -> list[LightroomMaskOperationResult]:
        if not value:
            raise ValueError("operation_results must not be empty")
        return value

    @model_validator(mode="after")
    def validate_mask_result(self) -> "LightroomMaskApplyResultPayload":
        applied_count = sum(1 for result in self.operation_results if result.status in {"applied", "reused"})
        failed_count = sum(1 for result in self.operation_results if result.status == "failed")
        skipped_count = sum(1 for result in self.operation_results if result.status == "skipped")

        if self.status == "applied" and applied_count != len(self.operation_results):
            raise ValueError("applied mask result requires all operations applied or reused")
        if self.status == "partial" and applied_count == 0:
            raise ValueError("partial mask result requires at least one applied or reused operation")
        if self.status == "skipped" and skipped_count != len(self.operation_results):
            raise ValueError("skipped mask result requires all operations skipped")
        if self.status == "failed" and failed_count == 0:
            raise ValueError("failed mask result requires at least one failed operation")
        if self.status == "failed" and not self.error_code:
            raise ValueError("failed mask result requires error_code")
        if applied_count and self.capability_snapshot.native_mask_command_supported is not True:
            raise ValueError("applied mask result requires native_mask_command_supported=true")
        return self
