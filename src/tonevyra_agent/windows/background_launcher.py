"""Launch the T-030 background worker from the Windows tray shell boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings
from tonevyra_agent.windows.single_instance import SingleInstanceGuard, per_user_mutex_name


def build_background_command(executable: Path | None = None, *, frozen: bool | None = None) -> list[str]:
    runtime_executable = executable or Path(sys.executable)
    frozen_runtime = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen_runtime:
        return [str(runtime_executable), "background"]
    return [str(runtime_executable), "-m", "tonevyra_agent.cli", "background"]


@dataclass
class BackgroundWorkerLauncher:
    """Process launcher only; the background runtime owns all pipeline behavior."""

    settings: Settings | None = None
    process: subprocess.Popen | None = None

    def is_background_running(self) -> bool:
        """Return True when the per-user background Agent mutex is already owned."""

        config = self.settings or get_settings()
        with SingleInstanceGuard(per_user_mutex_name("Agent"), config) as guard:
            return not guard.acquired

    def start(self) -> subprocess.Popen:
        if self.process is not None and self.process.poll() is None:
            return self.process
        env = os.environ.copy()
        if getattr(sys, "frozen", False):
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        source_path = str(PROJECT_ROOT / "src")
        env["PYTHONPATH"] = source_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        config = self.settings or get_settings()
        log_dir = config.project_path(config.runtime_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = (log_dir / "tonevyra_background.stdout.log").open("a", encoding="utf-8")
        stderr = (log_dir / "tonevyra_background.stderr.log").open("a", encoding="utf-8")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            build_background_command(),
            cwd=PROJECT_ROOT,
            env=env,
            creationflags=creationflags,
            stdout=stdout,
            stderr=stderr,
        )
        return self.process

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        config = self.settings or get_settings()
        self.process.terminate()
        try:
            self.process.wait(timeout=config.graceful_shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
