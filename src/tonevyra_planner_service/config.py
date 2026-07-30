"""Configuration for the loopback Planner Service executable."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


def _default_data_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if getattr(sys, "frozen", False) and local_appdata:
        return Path(local_appdata) / "TonevyraAI" / "planner_server"
    project_root = Path(os.environ.get("TONEVYRA_PROJECT_ROOT", Path.cwd()))
    return project_root / "runtime" / "planner_server"


@dataclass(frozen=True)
class PlannerServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str = "secret-key"
    data_dir: Path = _default_data_dir()
    planner_version: str = "rule-planner-v1"
    policy_version: str = "local-reference"
    max_request_body_bytes: int = 262_144

    @classmethod
    def from_env(cls) -> "PlannerServerConfig":
        host = os.environ.get("TONEVYRA_PLANNER_SERVER_HOST", "127.0.0.1")
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Local Planner Service may bind to a loopback address only.")
        return cls(
            host=host,
            port=int(os.environ.get("TONEVYRA_PLANNER_SERVER_PORT", "8000")),
            api_key=os.environ.get("TONEVYRA_PLANNER_API_KEY", "secret-key"),
            data_dir=Path(os.environ.get("TONEVYRA_PLANNER_SERVER_DATA_DIR", _default_data_dir())),
        )
