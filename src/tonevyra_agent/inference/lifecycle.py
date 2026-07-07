"""Bounded inference worker lifecycle controller for T-031."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings


class InferenceWorkerState(str, Enum):
    UNLOADED = "UNLOADED"
    STARTING = "STARTING"
    READY = "READY"
    IDLE_GRACE = "IDLE_GRACE"
    STOPPING = "STOPPING"


@dataclass(frozen=True)
class InferenceWorkerSnapshot:
    state: InferenceWorkerState
    pid: int | None
    max_workers: int
    started_count: int
    stopped_count: int


class ProcessInferenceWorkerController:
    """Starts one model-owning child process only when durable work exists."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        executable: Path | None = None,
        command_override: list[str] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.executable = executable or Path(sys.executable)
        self.command_override = command_override
        self.process: subprocess.Popen | None = None
        self.started_count = 0
        self.stopped_count = 0
        self.state = InferenceWorkerState.UNLOADED

    def ensure_started(self) -> subprocess.Popen:
        if self.settings.max_inference_workers != 1:
            raise RuntimeError("T-031 MVP permits exactly one inference worker.")
        if self.process is not None and self.process.poll() is None:
            return self.process
        self._observe_exit()
        self.state = InferenceWorkerState.STARTING
        runtime_dir = self.settings.project_path(self.settings.runtime_dir)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        stdout = (runtime_dir / "tonevyra_inference_worker.stdout.log").open("a", encoding="utf-8")
        stderr = (runtime_dir / "tonevyra_inference_worker.stderr.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            self._command(),
            cwd=PROJECT_ROOT,
            env=self._env(),
            stdout=stdout,
            stderr=stderr,
            creationflags=_creationflags(),
        )
        self.started_count += 1
        self.state = InferenceWorkerState.READY
        return self.process

    def tick(self) -> InferenceWorkerSnapshot:
        self._observe_exit()
        return self.snapshot()

    def force_stop(self, *, timeout_seconds: float | None = None) -> None:
        if self.process is None or self.process.poll() is not None:
            self._observe_exit()
            return
        self.state = InferenceWorkerState.STOPPING
        timeout = timeout_seconds if timeout_seconds is not None else self.settings.graceful_shutdown_timeout_seconds
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self._observe_exit()

    def wait_for_unloaded(self, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.tick().state == InferenceWorkerState.UNLOADED:
                return True
            time.sleep(0.05)
        return self.tick().state == InferenceWorkerState.UNLOADED

    def snapshot(self) -> InferenceWorkerSnapshot:
        pid = self.process.pid if self.process is not None and self.process.poll() is None else None
        return InferenceWorkerSnapshot(
            state=self.state,
            pid=pid,
            max_workers=self.settings.max_inference_workers,
            started_count=self.started_count,
            stopped_count=self.stopped_count,
        )

    def _observe_exit(self) -> None:
        if self.process is None:
            self.state = InferenceWorkerState.UNLOADED
            return
        if self.process.poll() is None:
            return
        self.process = None
        self.stopped_count += 1
        self.state = InferenceWorkerState.UNLOADED

    def _command(self) -> list[str]:
        if self.command_override is not None:
            return self.command_override
        if getattr(sys, "frozen", False):
            return [str(self.executable), "inference-worker"]
        return [str(self.executable), "-m", "tonevyra_agent.inference.worker_process", "run"]

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        source_path = str(PROJECT_ROOT / "src")
        env["PYTHONPATH"] = source_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["TONEVYRA_PROJECT_ROOT"] = str(PROJECT_ROOT)
        env["TONEVYRA_INFERENCE_IDLE_GRACE_SECONDS"] = str(self.settings.inference_idle_grace_seconds)
        return env


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
