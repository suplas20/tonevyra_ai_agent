from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.agent.loops import (
    IMPLEMENTED_MVP_LOOPS,
    PROCESSING_LOOP,
    QUALITY_LOOP,
    RECOVERY_LOOP,
    WATCH_LOOP,
    is_loop_payload,
    validate_loop_payload,
)
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskEventRepository

DEFAULT_SMOKE_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "smoke_t010"
DEFAULT_SMOKE_MANIFEST = DEFAULT_SMOKE_RUNTIME_DIR / "smoke_result.json"
DEFAULT_RECOVERY_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "recovery_t011"
RECOVERY_FILE_NAMES = (
    "recovery_analysis_has_vision.jpg",
    "recovery_lightroom_response.jpg",
    "recovery_missing_export.jpg",
)
TERMINAL_RECOVERY_FILE_NAME = "recovery_terminal_pass.jpg"


def _settings(runtime_dir: Path) -> Settings:
    return Settings(
        runtime_dir=runtime_dir,
        input_dir=runtime_dir / "input",
        output_dir=runtime_dir / "output",
        artifact_dir=runtime_dir / "artifacts",
        preview_dir=runtime_dir / "previews",
        bridge_dir=runtime_dir / "bridge",
        log_dir=runtime_dir / "logs",
        models_dir=PROJECT_ROOT / "models",
        vision_backend="mock",
        lightroom_backend="fake",
    )


def _run_supporting_harnesses(smoke_runtime_dir: Path, recovery_runtime_dir: Path) -> None:
    commands = (
        [
            sys.executable,
            str(PROJECT_ROOT / "harness" / "scripts" / "run_smoke_pipeline.py"),
            "--runtime-dir",
            str(smoke_runtime_dir),
        ],
        [
            sys.executable,
            str(PROJECT_ROOT / "harness" / "scripts" / "run_recovery_test.py"),
            "--runtime-dir",
            str(recovery_runtime_dir),
        ],
    )
    for command in commands:
        completed = subprocess.run(command, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            raise RuntimeError(f"supporting harness failed: {' '.join(command)}")


def _load_smoke_task_id(manifest_path: Path) -> UUID:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return UUID(payload["task_id"])


def _task_ids_by_file_names(settings: Settings, file_names: tuple[str, ...]) -> dict[str, UUID]:
    task_repo = ImageTaskRepository()
    result: dict[str, UUID] = {}
    with session_scope(settings) as session:
        for file_name in file_names:
            tasks = task_repo.list_by_file_name(session, file_name)
            if len(tasks) != 1:
                raise RuntimeError(f"expected one task for {file_name}, got {len(tasks)}")
            result[file_name] = tasks[0].id
    return result


def _verify_task_loop_payloads(settings: Settings, task_id: UUID, *, required_loops: set[str]) -> set[str]:
    task_repo = ImageTaskRepository()
    event_repo = TaskEventRepository()
    seen_loops: set[str] = set()
    errors: list[str] = []

    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task does not exist: {task_id}")

        events = event_repo.list_for_task(session, task_id)
        for event in events:
            payload = event.payload_json or {}
            if not is_loop_payload(payload):
                continue

            seen_loops.add(payload["loop_name"])
            validation = validate_loop_payload(payload, event_type=event.event_type)
            if not validation.ok:
                errors.append(f"{event.id} {event.event_type}: {list(validation.errors)}")

        missing = required_loops - seen_loops
        if missing:
            errors.append(f"task {task_id} missing loop evidence: {sorted(missing)}")

        unknown = seen_loops - IMPLEMENTED_MVP_LOOPS
        if unknown:
            errors.append(f"task {task_id} has unexpected implemented loop evidence: {sorted(unknown)}")

    if errors:
        raise RuntimeError("; ".join(errors))
    return seen_loops


def _verify_terminal_task_has_no_recovery_loop(settings: Settings, task_id: UUID) -> None:
    task_repo = ImageTaskRepository()
    event_repo = TaskEventRepository()
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"terminal recovery task does not exist: {task_id}")
        if task.status != TaskStatus.PASS.value:
            raise RuntimeError(f"terminal recovery task status changed unexpectedly: {task.status}")
        events = event_repo.list_for_task(session, task_id)
        if any((event.payload_json or {}).get("loop_name") == RECOVERY_LOOP for event in events):
            raise RuntimeError("terminal task should not have recovery_loop evidence")


def _print_ok(message: str) -> None:
    print(f"OK {message}")


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify product loop evidence in task_events.")
    parser.add_argument("--smoke-manifest", type=Path, default=DEFAULT_SMOKE_MANIFEST)
    parser.add_argument("--smoke-runtime-dir", type=Path, default=DEFAULT_SMOKE_RUNTIME_DIR)
    parser.add_argument("--recovery-runtime-dir", type=Path, default=DEFAULT_RECOVERY_RUNTIME_DIR)
    parser.add_argument("--skip-run", action="store_true", help="Verify existing smoke/recovery harness rows without rerunning them.")
    parser.add_argument("--task-id", action="append", default=None, help="Verify specific task id only.")
    parser.add_argument("--require-loop", action="append", default=None)
    args = parser.parse_args()

    try:
        smoke_runtime_dir = args.smoke_runtime_dir.resolve()
        recovery_runtime_dir = args.recovery_runtime_dir.resolve()
        if not args.skip_run and args.task_id is None:
            _run_supporting_harnesses(smoke_runtime_dir, recovery_runtime_dir)

        if args.task_id:
            required = set(args.require_loop or [])
            settings = _settings(smoke_runtime_dir)
            all_seen: set[str] = set()
            for raw_task_id in args.task_id:
                all_seen.update(_verify_task_loop_payloads(settings, UUID(raw_task_id), required_loops=required))
            _print_ok(f"loop event verification complete for explicit tasks: seen={sorted(all_seen)}")
            return 0

        smoke_settings = _settings(smoke_runtime_dir)
        smoke_task_id = _load_smoke_task_id(args.smoke_manifest.resolve())
        smoke_seen = _verify_task_loop_payloads(
            smoke_settings,
            smoke_task_id,
            required_loops={WATCH_LOOP, PROCESSING_LOOP, QUALITY_LOOP},
        )
        _print_ok(f"smoke loop evidence verified for {smoke_task_id}: {sorted(smoke_seen)}")

        recovery_settings = _settings(recovery_runtime_dir)
        recovery_task_ids = _task_ids_by_file_names(recovery_settings, RECOVERY_FILE_NAMES)
        for file_name, task_id in recovery_task_ids.items():
            seen = _verify_task_loop_payloads(recovery_settings, task_id, required_loops={RECOVERY_LOOP})
            _print_ok(f"recovery loop evidence verified for {file_name}: {sorted(seen)}")

        terminal_task_id = _task_ids_by_file_names(recovery_settings, (TERMINAL_RECOVERY_FILE_NAME,))[TERMINAL_RECOVERY_FILE_NAME]
        _verify_terminal_task_has_no_recovery_loop(recovery_settings, terminal_task_id)
        _print_ok("terminal recovery task has no automatic recovery_loop evidence")

        print("Loop event verification complete.")
        return 0
    except Exception as exc:
        return _fail(f"Loop event verification failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
