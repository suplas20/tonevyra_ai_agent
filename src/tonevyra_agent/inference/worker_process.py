"""Inference worker child process entry point.

This process owns model runtime imports and exits after a bounded idle grace.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from tonevyra_agent.agent.runner import AgentRunner
from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings
from tonevyra_agent.core.enums import TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository
from tonevyra_agent.windows.single_instance import SingleInstanceGuard, per_user_mutex_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tonevyra AI inference worker process")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--idle-grace", type=float, default=None)
    run_parser.add_argument("--poll-interval", type=float, default=0.5)
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_until_idle(idle_grace=args.idle_grace, poll_interval=args.poll_interval)
    return 2


def run_until_idle(*, idle_grace: float | None = None, poll_interval: float = 0.5) -> int:
    settings = get_settings()
    grace_seconds = settings.inference_idle_grace_seconds if idle_grace is None else idle_grace
    lifecycle_log = settings.project_path(settings.runtime_dir) / "inference_worker_lifecycle.jsonl"
    lifecycle_log.parent.mkdir(parents=True, exist_ok=True)
    with SingleInstanceGuard(per_user_mutex_name("InferenceWorker"), settings) as guard:
        if not guard.acquired:
            _append_event(lifecycle_log, {"event": "duplicate_blocked", "pid": os.getpid()})
            return 3
        last_activity = time.monotonic()
        _append_event(lifecycle_log, {"event": "started", "pid": os.getpid(), "idle_grace_seconds": grace_seconds})
        try:
            while True:
                queued = _queued_count(settings)
                if queued > 0:
                    _append_event(lifecycle_log, {"event": "processing_start", "pid": os.getpid(), "queued": queued})
                    with _fake_lightroom_worker(settings):
                        result = AgentRunner(settings=settings).run_once(scan_input=False)
                    processed = bool(result.worker_result and result.worker_result.processed)
                    _append_event(lifecycle_log, {"event": "processing_done", "pid": os.getpid(), "processed": processed})
                    last_activity = time.monotonic()
                    continue
                if not settings.keep_model_warm and time.monotonic() - last_activity >= grace_seconds:
                    _append_event(lifecycle_log, {"event": "idle_unload", "pid": os.getpid()})
                    return 0
                time.sleep(poll_interval)
        finally:
            _append_event(lifecycle_log, {"event": "stopped", "pid": os.getpid()})


def _queued_count(settings: Settings) -> int:
    with session_scope(settings) as session:
        return len(ImageTaskRepository().list_by_status(session, TaskStatus.QUEUED))


def _append_event(path: Path, payload: dict) -> None:
    payload = {"schema_version": "t031.inference_worker_lifecycle.v1", "time_epoch": time.time(), **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


@contextmanager
def _fake_lightroom_worker(settings: Settings):
    process: subprocess.Popen | None = None
    if settings.lightroom_backend == "fake":
        command = [
            sys.executable,
            str(PROJECT_ROOT / "harness" / "fake_lightroom" / "fake_lightroom_worker.py"),
            "--bridge-dir",
            str(settings.project_path(settings.bridge_dir)),
            "--poll-interval",
            "0.1",
        ]
        env = os.environ.copy()
        env["TONEVYRA_BRIDGE_DIR"] = str(settings.project_path(settings.bridge_dir))
        process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, creationflags=_creationflags())
    try:
        yield
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


if __name__ == "__main__":
    raise SystemExit(main())

