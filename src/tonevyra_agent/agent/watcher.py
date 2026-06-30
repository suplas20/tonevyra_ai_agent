"""Folder scanning, file stabilization, and task registration."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, Stage, TaskEventType, TaskStatus
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskEventRepository


IGNORED_NAMES = {".DS_Store"}
IGNORED_SUFFIXES = {".tmp", ".part", ".crdownload", ".xmp"}
WATCH_LOOP_NAME = "watch_loop"


@dataclass(frozen=True)
class FileStabilityResult:
    stable: bool
    size_bytes: int | None = None
    reason: str | None = None


@dataclass
class WatchScanResult:
    created_task_ids: list[str] = field(default_factory=list)
    requeued_task_ids: list[str] = field(default_factory=list)
    skipped_task_ids: list[str] = field(default_factory=list)
    ignored_paths: list[Path] = field(default_factory=list)
    duplicate_paths: list[Path] = field(default_factory=list)
    unstable_paths: list[Path] = field(default_factory=list)


def parse_supported_extensions(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def is_ignored_file(path: Path) -> bool:
    name = path.name
    if name in IGNORED_NAMES:
        return True
    if name.startswith(".") or name.startswith("._"):
        return True
    return path.suffix.lower() in IGNORED_SUFFIXES


def is_supported_photo(path: Path, supported_extensions: set[str] | None = None) -> bool:
    extensions = supported_extensions or parse_supported_extensions(get_settings().supported_extensions)
    return path.is_file() and path.suffix.lower() in extensions


def calculate_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wait_for_stable_file(
    path: Path,
    *,
    required_checks: int,
    interval_seconds: float,
    timeout_seconds: float,
) -> FileStabilityResult:
    if required_checks < 2:
        required_checks = 2

    deadline = time.monotonic() + timeout_seconds
    last_size: int | None = None
    stable_observations = 0

    while time.monotonic() <= deadline:
        try:
            stat = path.stat()
            with path.open("rb") as handle:
                handle.read(1)
        except OSError as exc:
            return FileStabilityResult(stable=False, reason=str(exc))

        if stat.st_size == last_size:
            stable_observations += 1
        else:
            stable_observations = 1
            last_size = stat.st_size

        if stable_observations >= required_checks:
            return FileStabilityResult(stable=True, size_bytes=stat.st_size)

        time.sleep(interval_seconds)

    return FileStabilityResult(stable=False, size_bytes=last_size, reason="file size did not stabilize before timeout")


class FolderWatcher:
    """One-shot scanner used by CLI and harness before the continuous loop exists."""

    def __init__(
        self,
        settings: Settings | None = None,
        task_repository: ImageTaskRepository | None = None,
        event_repository: TaskEventRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.task_repository = task_repository or ImageTaskRepository()
        self.event_repository = event_repository or TaskEventRepository()
        self.supported_extensions = parse_supported_extensions(self.settings.supported_extensions)

    def scan_once(self, session: Session, input_dir: Path | None = None) -> WatchScanResult:
        root = self.settings.project_path(input_dir or self.settings.input_dir)
        result = WatchScanResult()
        if not root.exists():
            return result

        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if is_ignored_file(path):
                result.ignored_paths.append(path)
                continue

            if not is_supported_photo(path, self.supported_extensions):
                task = self._register_unsupported_file(session, path)
                result.skipped_task_ids.append(str(task.id))
                continue

            stability = wait_for_stable_file(
                path,
                required_checks=self.settings.file_stable_checks,
                interval_seconds=self.settings.file_stable_interval_seconds,
                timeout_seconds=self.settings.file_stable_timeout_seconds,
            )
            if not stability.stable:
                result.unstable_paths.append(path)
                continue

            source_hash = calculate_file_sha256(path)
            source_path = str(path.resolve())
            file_arrived_at = _file_arrival_timestamp(path)
            existing = self.task_repository.get_by_source_path_hash(session, source_path, source_hash)
            if existing is not None:
                if _exact_source_match_should_requeue(existing, file_mtime=file_arrived_at):
                    task = self._requeue_existing_supported_file(
                        session,
                        existing,
                        source_path=source_path,
                        source_hash=source_hash,
                        file_arrived_at=file_arrived_at,
                    )
                    result.requeued_task_ids.append(str(task.id))
                else:
                    result.duplicate_paths.append(path)
                continue

            if self.task_repository.get_non_failed_by_source_hash(session, source_hash) is not None:
                result.duplicate_paths.append(path)
                continue

            task = self._register_supported_file(
                session,
                path,
                source_path=source_path,
                source_hash=source_hash,
                file_size_bytes=stability.size_bytes,
            )
            result.created_task_ids.append(str(task.id))

        return result

    def _is_duplicate(self, session: Session, *, source_path: str, source_hash: str, file_mtime: float | None = None) -> bool:
        existing = self.task_repository.get_by_source_path_hash(session, source_path, source_hash)
        if existing is not None:
            return _exact_source_match_is_duplicate(existing, file_mtime=file_mtime)
        return self.task_repository.get_non_failed_by_source_hash(session, source_hash) is not None

    def _register_supported_file(
        self,
        session: Session,
        path: Path,
        *,
        source_path: str,
        source_hash: str,
        file_size_bytes: int | None,
    ):
        task = self.task_repository.create(
            session,
            source_path=source_path,
            source_hash=source_hash,
            file_name=path.name,
            file_ext=path.suffix.lower(),
            file_size_bytes=file_size_bytes,
            status=TaskStatus.QUEUED,
            current_stage=Stage.WATCH,
        )

        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_CREATED,
            stage=Stage.WATCH,
            message="Supported image file stabilized and queued.",
            payload_json={
                "loop_name": WATCH_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.TASK_CREATED.value,
                "from_status": TaskStatus.DETECTED.value,
                "to_status": TaskStatus.QUEUED.value,
                "reason": "supported file stabilized",
                "source_path": source_path,
                "source_hash": source_hash,
                "evidence_artifacts": [],
            },
        )
        return task

    def _requeue_existing_supported_file(
        self,
        session: Session,
        task,
        *,
        source_path: str,
        source_hash: str,
        file_arrived_at: float,
    ):
        previous_status = task.status
        self.task_repository.requeue_for_retry(session, task)
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_RETRIED,
            stage=Stage.WATCH,
            message="Existing failed image task was requeued after the source file was re-dropped.",
            payload_json={
                "loop_name": WATCH_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.TASK_RETRIED.value,
                "from_status": previous_status,
                "to_status": TaskStatus.QUEUED.value,
                "reason": "source file arrival time is newer than previous failed task update",
                "source_path": source_path,
                "source_hash": source_hash,
                "file_arrived_at": datetime.fromtimestamp(file_arrived_at).isoformat(timespec="seconds"),
                "retry_count": task.retry_count,
                "evidence_artifacts": [],
            },
        )
        return task

    def _register_unsupported_file(self, session: Session, path: Path):
        source_path = str(path.resolve())
        source_hash = calculate_file_sha256(path)
        if self._is_duplicate(session, source_path=source_path, source_hash=source_hash, file_mtime=_file_arrival_timestamp(path)):
            existing = (
                self.task_repository.get_by_source_path_hash(session, source_path, source_hash)
                or self.task_repository.get_non_failed_by_source_hash(session, source_hash)
            )
            if existing is not None:
                return existing

        task = self.task_repository.create(
            session,
            source_path=source_path,
            source_hash=source_hash,
            file_name=path.name,
            file_ext=path.suffix.lower(),
            file_size_bytes=path.stat().st_size,
            status=TaskStatus.SKIPPED,
            current_stage=Stage.WATCH,
            error_code=ErrorCode.UNSUPPORTED_FILE_TYPE.value,
            error_message=f"Unsupported file type: {path.suffix.lower()}",
            failed_stage=Stage.WATCH,
            completed_at=datetime.utcnow(),
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_SKIPPED,
            stage=Stage.WATCH,
            message="Unsupported visible file skipped.",
            payload_json={
                "loop_name": WATCH_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.TASK_SKIPPED.value,
                "from_status": TaskStatus.DETECTED.value,
                "to_status": TaskStatus.SKIPPED.value,
                "reason": ErrorCode.UNSUPPORTED_FILE_TYPE.value,
                "source_path": source_path,
                "source_hash": source_hash,
                "evidence_artifacts": [],
            },
        )
        return task


def _exact_source_match_is_duplicate(existing, *, file_mtime: float | None) -> bool:
    """Decide whether an exact path/hash task should block a new watch task.

    A previously failed task blocks normal repeated scans to avoid unbounded
    retry loops. If the source file was written after that failure, treat it as
    an operator re-drop/replacement and allow a new task even when the filename
    and content hash are the same.
    """

    return not _exact_source_match_should_requeue(existing, file_mtime=file_mtime)


def _exact_source_match_should_requeue(existing, *, file_mtime: float | None) -> bool:
    if getattr(existing, "status", None) != TaskStatus.FAILED.value:
        return False
    updated_at = getattr(existing, "updated_at", None)
    if file_mtime is None or updated_at is None:
        return False
    return file_mtime > _datetime_timestamp(updated_at) + 1.0


def _datetime_timestamp(value: datetime) -> float:
    return value.timestamp()


def _file_arrival_timestamp(path: Path) -> float:
    stat = path.stat()
    return max(stat.st_mtime, stat.st_ctime)
