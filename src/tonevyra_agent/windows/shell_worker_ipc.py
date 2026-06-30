"""Validated local command envelope for T-030 Tray/CLI operations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TrayCommandName(StrEnum):
    GET_STATUS = "GET_STATUS"
    PAUSE_WATCHING = "PAUSE_WATCHING"
    RESUME_WATCHING = "RESUME_WATCHING"
    RESCAN = "RESCAN"
    OPEN_INPUT_FOLDER = "OPEN_INPUT_FOLDER"
    OPEN_OUTPUT_FOLDER = "OPEN_OUTPUT_FOLDER"
    RETRY_FAILED_JOB = "RETRY_FAILED_JOB"
    SHUTDOWN = "SHUTDOWN"


class TrayCommandStatus(StrEnum):
    APPLIED = "APPLIED"
    NO_OP = "NO_OP"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class TrayCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t030.tray_command.v1"] = "t030.tray_command.v1"
    command_id: str = Field(default_factory=lambda: str(uuid4()))
    command: TrayCommandName
    requested_at: str = Field(default_factory=utc_now)
    source: Literal["TRAY", "CLI", "INSTALLER"] = "TRAY"
    expected_agent_instance_id: str | None = None
    job_id: str | None = None


class TrayCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    status: TrayCommandStatus
    agent_state: str
    idempotent_replay: bool = False
    error_code: str | None = None
    message: str = ""


class TrayCommandProcessor:
    """Small in-process command handler with idempotent command_id replay."""

    def __init__(self) -> None:
        self._results: dict[str, TrayCommandResult] = {}

    def handle(self, command: TrayCommand, *, current_state: str, apply) -> TrayCommandResult:
        previous = self._results.get(command.command_id)
        if previous is not None:
            return previous.model_copy(update={"idempotent_replay": True})
        try:
            next_state, message = apply(command)
            result = TrayCommandResult(
                command_id=command.command_id,
                status=TrayCommandStatus.APPLIED if next_state != current_state else TrayCommandStatus.NO_OP,
                agent_state=next_state,
                message=message,
            )
        except Exception as exc:  # noqa: BLE001 - command failures are reported, not raised to tray
            result = TrayCommandResult(
                command_id=command.command_id,
                status=TrayCommandStatus.FAILED,
                agent_state=current_state,
                error_code="TRAY_IPC_UNAVAILABLE",
                message=str(exc),
            )
        self._results[command.command_id] = result
        return result
