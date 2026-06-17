from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.agent.watcher import FolderWatcher
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ErrorCode, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskEventRepository


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "watcher_t003"
IGNORED_FIXTURES = ["ignore.tmp", "sidecar.xmp", ".DS_Store", "._resource", "download.crdownload", "partial.part"]
UNSUPPORTED_FIXTURE = "operator_note.txt"


def _settings() -> Settings:
    return Settings(
        runtime_dir=RUNTIME_DIR,
        input_dir=RUNTIME_DIR / "input",
        output_dir=RUNTIME_DIR / "output",
        artifact_dir=RUNTIME_DIR / "artifacts",
        preview_dir=RUNTIME_DIR / "previews",
        bridge_dir=RUNTIME_DIR / "bridge",
        log_dir=RUNTIME_DIR / "logs",
        models_dir=PROJECT_ROOT / "models",
        file_stable_checks=2,
        file_stable_interval_seconds=0.01,
        file_stable_timeout_seconds=2.0,
    )


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)


def _cleanup_db(settings: Settings, names: list[str]) -> None:
    repo = ImageTaskRepository()
    with session_scope(settings) as session:
        for name in names:
            for task in repo.list_by_file_name(session, name):
                repo.delete(session, task)


def _prepare_input(settings: Settings) -> Path:
    input_dir = settings.project_path(settings.input_dir)
    shutil.copy2(FIXTURE_IMAGE, input_dir / FIXTURE_IMAGE.name)
    for name in IGNORED_FIXTURES:
        (input_dir / name).write_text("ignored by watcher harness", encoding="utf-8")
    (input_dir / UNSUPPORTED_FIXTURE).write_text("unsupported visible file", encoding="utf-8")
    return input_dir


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    names = [FIXTURE_IMAGE.name, UNSUPPORTED_FIXTURE, *IGNORED_FIXTURES]
    _cleanup_db(settings, names)
    _reset_runtime(settings)
    input_dir = _prepare_input(settings)

    watcher = FolderWatcher(settings=settings)
    task_repo = ImageTaskRepository()
    event_repo = TaskEventRepository()

    with session_scope(settings) as session:
        result = watcher.scan_once(session, input_dir)

    print(f"OK watcher scan completed in {input_dir}")
    print(f"created_task_ids={result.created_task_ids}")
    print(f"skipped_task_ids={result.skipped_task_ids}")
    print(f"ignored_count={len(result.ignored_paths)}")

    with session_scope(settings) as session:
        supported_tasks = task_repo.list_by_file_name(session, FIXTURE_IMAGE.name)
        unsupported_tasks = task_repo.list_by_file_name(session, UNSUPPORTED_FIXTURE)
        ignored_tasks = []
        for name in IGNORED_FIXTURES:
            ignored_tasks.extend(task_repo.list_by_file_name(session, name))

        if len(supported_tasks) != 1:
            return _fail(f"expected 1 supported image task, got {len(supported_tasks)}")
        supported = supported_tasks[0]
        if supported.status != TaskStatus.QUEUED.value:
            return _fail(f"supported task status should be QUEUED, got {supported.status}")
        supported_events = event_repo.list_for_task(session, supported.id)
        if not any(event.payload_json.get("loop_name") == "watch_loop" for event in supported_events):
            return _fail("supported task is missing watch_loop event evidence")

        if len(unsupported_tasks) != 1:
            return _fail(f"expected 1 unsupported SKIPPED task, got {len(unsupported_tasks)}")
        unsupported = unsupported_tasks[0]
        if unsupported.status != TaskStatus.SKIPPED.value:
            return _fail(f"unsupported task status should be SKIPPED, got {unsupported.status}")
        if unsupported.error_code != ErrorCode.UNSUPPORTED_FILE_TYPE.value:
            return _fail(f"unsupported task error_code should be UNSUPPORTED_FILE_TYPE, got {unsupported.error_code}")

        if ignored_tasks:
            return _fail(f"ignored files created tasks: {[task.file_name for task in ignored_tasks]}")

    with session_scope(settings) as session:
        second = watcher.scan_once(session, input_dir)
        if second.created_task_ids:
            return _fail(f"second scan should not create duplicates, got {second.created_task_ids}")

    print("OK supported image task created")
    print("OK unsupported visible file skipped")
    print("OK ignored files did not create tasks")
    print("OK duplicate scan did not create tasks")

    _cleanup_db(settings, names)
    print("OK watcher test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
