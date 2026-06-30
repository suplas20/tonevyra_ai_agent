"""T-030 runtime snapshot schema and persistence helpers."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tonevyra_agent.agent.runtime_state import AgentRuntimeState
from tonevyra_agent.core.config import Settings, get_settings


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class AgentRuntimeSnapshot(BaseModel):
    """Machine-readable status consumed by tray, CLI, and T-030 harness."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t030.agent_runtime_snapshot.v1"] = "t030.agent_runtime_snapshot.v1"
    agent_instance_id: str
    shell_instance_id: str | None = None
    state: AgentRuntimeState
    started_at: str = Field(default_factory=utc_now)
    last_heartbeat_at: str = Field(default_factory=utc_now)
    watching_enabled: bool
    watch_path: str
    recursive: bool = False
    queue_depth: int = Field(ge=0)
    processing_count: int = Field(ge=0, le=1)
    failed_count: int = Field(ge=0)
    active_job_id: str | None = None
    lightroom_connected: bool
    model_ready: bool
    db_ready: bool
    degraded_reasons: list[str] = Field(default_factory=list)
    worker_restart_count: int = Field(default=0, ge=0)
    version: str = "0.30.0"

    @model_validator(mode="after")
    def validate_state_consistency(self) -> "AgentRuntimeSnapshot":
        if self.state == AgentRuntimeState.PROCESSING and self.processing_count == 0 and self.active_job_id is None:
            raise ValueError("PROCESSING requires processing_count > 0 or active_job_id")
        if self.state == AgentRuntimeState.DEGRADED and not self.degraded_reasons:
            raise ValueError("DEGRADED requires degraded_reasons")
        if self.state == AgentRuntimeState.STOPPED and self.watching_enabled:
            raise ValueError("STOPPED requires watching_enabled=false")
        if len(self.degraded_reasons) != len(set(self.degraded_reasons)):
            raise ValueError("degraded_reasons must be unique")
        return self


class RuntimeSnapshotStore:
    """Atomic file store for the latest runtime snapshot."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = self.settings.project_path(self.settings.runtime_dir) / "agent_runtime_snapshot.json"

    def write(self, snapshot: AgentRuntimeSnapshot) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        temp_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            delete=False,
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self.path)
        return self.path

    def read(self) -> AgentRuntimeSnapshot | None:
        if not self.path.exists():
            return None
        return AgentRuntimeSnapshot.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
