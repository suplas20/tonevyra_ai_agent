"""Lightroom bridge payload schemas."""

from pathlib import Path

from pydantic import BaseModel, Field

from mw_photo_agent.core.enums import LightroomCommand


class LightroomRequest(BaseModel):
    request_id: str
    task_id: str
    command: LightroomCommand
    source_path: Path | None = None
    export_path: Path | None = None
    adjustments: dict[str, float] = Field(default_factory=dict)


class LightroomResponse(BaseModel):
    request_id: str
    task_id: str
    ok: bool
    export_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None

