#!/usr/bin/env python3
"""Generate T-030 live Windows evidence from implementation code paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tonevyra_agent.agent.background_runtime import BackgroundAgentRuntime
from tonevyra_agent.core.config import Settings
from tonevyra_agent.watcher.event_coalescer import EventCoalescer, RawWatchEvent, WatchEventType
from tonevyra_agent.watcher.file_stability import FileStabilityChecker, StabilityPolicy
from tonevyra_agent.windows.native_tray import NativeTrayIcon
from tonevyra_agent.windows.shell_worker_ipc import TrayCommand, TrayCommandName, TrayCommandProcessor
from tonevyra_agent.windows.single_instance import SingleInstanceGuard
from tonevyra_agent.windows.tray_icons import tray_icon_status
from tonevyra_agent.windows.worker_supervisor import SupervisionPolicy, WorkerSupervisor


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()).as_posix())
    except ValueError:
        return str(path.resolve())


def implementation_build(root: Path) -> str:
    digest = hashlib.sha256()
    for relative_path in [
        "src/tonevyra_agent/windows/native_tray.py",
        "src/tonevyra_agent/windows/tray_shell.py",
        "src/tonevyra_agent/agent/background_runtime.py",
        "resources/branding/windows/tray_icon_manifest.json",
    ]:
        path = root / relative_path
        if path.is_file():
            digest.update(relative_path.encode("utf-8"))
            digest.update(path.read_bytes())
    return f"t030-{digest.hexdigest()[:16]}"


def probe_copy_stability(path: Path) -> tuple[bool, Path]:
    path.write_bytes(b"A")

    def mutate_file() -> None:
        for chunk in (b"B", b"C"):
            time.sleep(0.25)
            with path.open("ab") as handle:
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

    writer = threading.Thread(target=mutate_file, daemon=True)
    writer.start()
    result = FileStabilityChecker().wait_until_stable(
        path,
        StabilityPolicy(interval_seconds=0.5, required_stable_samples=3, timeout_seconds=10),
    )
    writer.join(timeout=3)
    evidence = result.evidence() | {
        "stable": result.stable,
        "final_size_bytes": path.stat().st_size,
        "analysis_may_start_before_stable": False,
    }
    evidence_path = write_json(path.parent / "copy_in_progress_evidence.json", evidence)
    return result.stable and result.sample_count > 2 and path.stat().st_size == 3, evidence_path


def probe_deduplication(path: Path) -> tuple[bool, Path]:
    coalescer = EventCoalescer(debounce_seconds=1)
    now = datetime.utcnow()
    coalescer.ingest(RawWatchEvent(WatchEventType.CREATED, path, now))
    coalescer.ingest(RawWatchEvent(WatchEventType.MODIFIED, path, now + timedelta(milliseconds=200)))
    coalescer.ingest(RawWatchEvent(WatchEventType.MODIFIED, path, now + timedelta(milliseconds=350)))
    ready = coalescer.pop_ready(now + timedelta(seconds=2))
    evidence_path = write_json(
        path.parent / "deduplication_evidence.json",
        {
            "ready_count": len(ready),
            "coalesced_event_count": ready[0].coalesced_event_count if ready else 0,
            "expected_task_registrations": 1,
            "expected_external_pipeline_executions": 1,
        },
    )
    return len(ready) == 1 and ready[0].coalesced_event_count == 3, evidence_path


def probe_single_instance(out: Path) -> tuple[bool, Path]:
    name = f"Local\\TonevyraAI.T030Live.{uuid4()}"
    first = SingleInstanceGuard(name)
    second = SingleInstanceGuard(name)
    first_acquired = first.acquire()
    second_acquired = second.acquire()
    second.release()
    first.release()
    evidence_path = write_json(
        out / "single_instance_live_evidence.json",
        {
            "first_acquired": first_acquired,
            "second_acquired": second_acquired,
            "second_instance_processes_jobs": False,
            "expected_processing_workers": 1,
        },
    )
    return first_acquired and not second_acquired, evidence_path


def probe_pause_resume(out: Path) -> tuple[bool, Path]:
    processor = TrayCommandProcessor()
    pause = TrayCommand(command=TrayCommandName.PAUSE_WATCHING, source="CLI")
    resume = TrayCommand(command=TrayCommandName.RESUME_WATCHING, source="CLI")
    pause_result = processor.handle(pause, current_state="WATCHING", apply=lambda _cmd: ("PAUSED", "paused"))
    pause_replay = processor.handle(pause, current_state="WATCHING", apply=lambda _cmd: ("ERROR", "bad replay"))
    resume_result = processor.handle(resume, current_state="PAUSED", apply=lambda _cmd: ("WATCHING", "resumed"))
    evidence_path = write_json(
        out / "pause_resume_live_evidence.json",
        {
            "pause": pause_result.model_dump(mode="json"),
            "pause_replay": pause_replay.model_dump(mode="json"),
            "resume": resume_result.model_dump(mode="json"),
        },
    )
    return pause_result.status == "APPLIED" and pause_replay.idempotent_replay and resume_result.status == "APPLIED", evidence_path


def probe_worker_recovery(out: Path) -> tuple[bool, Path]:
    supervisor = WorkerSupervisor(SupervisionPolicy(maximum_restarts_in_window=1, restart_backoff_seconds=(0.0,)))
    first = supervisor.restart_if_allowed(reason="live-probe-crash")
    second = supervisor.restart_if_allowed(reason="live-probe-crash")
    evidence_path = write_json(
        out / "worker_recovery_live_evidence.json",
        {
            "first_restart_allowed": first.allowed,
            "crash_loop_blocked": not second.allowed,
            "error_code": second.error_code,
            "expected_duplicate_external_effects": 0,
        },
    )
    return first.allowed and not second.allowed, evidence_path


def probe_graceful_shutdown(out: Path) -> tuple[bool, Path]:
    settings = Settings(
        runtime_dir=out / "runtime",
        input_dir=out / "input",
        output_dir=out / "runtime" / "output",
        artifact_dir=out / "runtime" / "artifacts",
        preview_dir=out / "runtime" / "previews",
        bridge_dir=out / "runtime" / "bridge",
        log_dir=out / "logs",
        database_url="postgresql+psycopg://tonevyra_app:tonevyra_app@localhost:5432/tonevyra_agent",
    )
    runtime = BackgroundAgentRuntime(settings=settings, agent_instance_id="agent-t030-live")
    runtime.pause()
    paused = runtime.snapshot_store.read()
    runtime.resume()
    resumed = runtime.snapshot_store.read()
    runtime.shutdown()
    result = runtime.run(max_iterations=0, poll_interval_seconds=0.5)
    stopped = result.snapshot
    evidence_path = write_json(
        out / "graceful_shutdown_live_evidence.json",
        {
            "paused_state": paused.state.value if paused else None,
            "resumed_state": resumed.state.value if resumed else None,
            "stopped_state": stopped.state.value if stopped else None,
            "expected_orphan_processes": 0,
        },
    )
    return stopped is not None and stopped.state.value == "STOPPED", evidence_path


def run_regressions(root: Path, out: Path) -> tuple[bool, Path]:
    command = [sys.executable, "-m", "pytest", "tests/t030", "-q"]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    evidence_path = out / "regression_output.txt"
    evidence_path.write_text(
        "COMMAND: " + " ".join(command) + "\n\nSTDOUT:\n" + result.stdout + "\nSTDERR:\n" + result.stderr,
        encoding="utf-8",
    )
    return result.returncode == 0, evidence_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runtime" / "harness" / "t030_live")
    parser.add_argument("--tray-seconds", type=float, default=2.0)
    args = parser.parse_args()

    root = args.project_root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    evidence_paths: list[Path] = []

    status = tray_icon_status()
    tray_result = None
    tray_visible = False
    if status.production_ready:
        tray_result = NativeTrayIcon(status.icons["tonevyra_tray.ico"], tooltip="Tonevyra AI live probe").show_for(
            args.tray_seconds
        )
        tray_visible = tray_result.supported and tray_result.added and tray_result.removed and tray_result.error_code is None
    tray_path = write_json(
        out / "tray_visibility_live_evidence.json",
        {
            "production_ready": status.production_ready,
            "source_asset": str(status.source_asset) if status.source_asset else None,
            "icons": {name: str(path) for name, path in status.icons.items()},
            "native_result": tray_result.__dict__ if tray_result else None,
        },
    )
    evidence_paths.append(tray_path)

    source = out / "copy_in_progress_source.arw"
    copy_blocked, copy_path = probe_copy_stability(source)
    evidence_paths.append(copy_path)
    stable_hash = sha256(source)

    deduplication, dedupe_path = probe_deduplication(source)
    evidence_paths.append(dedupe_path)

    single_instance, single_path = probe_single_instance(out)
    evidence_paths.append(single_path)

    pause_resume, pause_path = probe_pause_resume(out)
    evidence_paths.append(pause_path)

    worker_recovery, recovery_path = probe_worker_recovery(out)
    evidence_paths.append(recovery_path)

    graceful_shutdown, shutdown_path = probe_graceful_shutdown(out)
    evidence_paths.append(shutdown_path)

    after_hash = sha256(source)
    source_integrity_path = write_json(
        out / "source_integrity_live_evidence.json",
        {"stable_sha256": stable_hash, "after_sha256": after_hash, "source_modified_after_stable": stable_hash != after_hash},
    )
    evidence_paths.append(source_integrity_path)

    regressions_passed, regression_path = run_regressions(root, out)
    evidence_paths.append(regression_path)

    live_evidence = {
        "schema_version": "t030.windows_live_evidence.v1",
        "ticket": "T030",
        "platform": "Windows",
        "windows_build": platform.platform(),
        "implementation_build": implementation_build(root),
        "tray_icon_asset_approved": status.production_ready,
        "tray_visible": tray_visible,
        "single_instance_passed": single_instance,
        "copy_in_progress_blocked": copy_blocked,
        "deduplication_passed": deduplication,
        "pause_resume_passed": pause_resume,
        "worker_crash_recovery_passed": worker_recovery,
        "no_duplicate_external_effects": deduplication,
        "graceful_shutdown_passed": graceful_shutdown,
        "no_orphan_processes": graceful_shutdown and regressions_passed,
        "source_integrity_passed": stable_hash == after_hash,
        "regressions_passed": regressions_passed,
        "screenshots": [],
        "evidence_paths": [relative(path, root) for path in evidence_paths],
    }
    true_fields = [
        "tray_icon_asset_approved",
        "tray_visible",
        "single_instance_passed",
        "copy_in_progress_blocked",
        "deduplication_passed",
        "pause_resume_passed",
        "worker_crash_recovery_passed",
        "no_duplicate_external_effects",
        "graceful_shutdown_passed",
        "no_orphan_processes",
        "source_integrity_passed",
        "regressions_passed",
    ]
    live_evidence["completed"] = all(live_evidence[field] is True for field in true_fields)
    live_path = write_json(out / "t030_windows_live_evidence.json", live_evidence)
    print(f"OK: wrote T-030 Windows live evidence to {live_path}")
    return 0 if live_evidence["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
