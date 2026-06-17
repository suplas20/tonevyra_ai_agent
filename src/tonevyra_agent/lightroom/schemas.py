"""Schemas for the file-based Lightroom JSON bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tonevyra_agent.core.enums import ErrorCode


LIGHTROOM_COMMAND_PING = "PING"
LIGHTROOM_COMMAND_APPLY_ADJUSTMENTS_AND_EXPORT = "APPLY_ADJUSTMENTS_AND_EXPORT"
LIGHTROOM_RESPONSE_SUCCESS = "success"
LIGHTROOM_RESPONSE_FAILED = "failed"


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
