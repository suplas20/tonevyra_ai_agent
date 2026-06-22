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
LIGHTROOM_RESPONSE_SUCCESS = "success"
LIGHTROOM_RESPONSE_FAILED = "failed"
LIGHTROOM_APPLY_REQUEST_SCHEMA = "t019.lightroom_apply.request.v1"
LIGHTROOM_APPLY_RESULT_SCHEMA = "t019.lightroom_apply.result.v1"
LIGHTROOM_EXPORT_REQUEST_SCHEMA = "t020.lightroom_export.request.v1"
LIGHTROOM_EXPORT_RESULT_SCHEMA = "t020.lightroom_export.result.v1"

LIGHTROOM_APPLY_ALLOWED_SETTINGS = {
    "exposure",
    "contrast",
    "highlights",
    "shadows",
    "whites",
    "blacks",
    "temp",
    "tint",
    "vibrance",
    "saturation",
    "texture",
    "clarity",
    "dehaze",
    "sharpening",
    "noise_reduction",
}


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
