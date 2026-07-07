"""Thin runner helpers for one-shot Tonevyra AI agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from tonevyra_agent.agent.watcher import (
    WATCH_LOOP_NAME,
    FolderWatcher,
    WatchScanResult,
    calculate_file_sha256,
    is_supported_photo,
    wait_for_stable_file,
)
from tonevyra_agent.agent.worker import AgentWorker, WorkerPipelineResult
from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import Stage, TaskEventType, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskEventRepository
from tonevyra_agent.lightroom.process import lightroom_classic_status


@dataclass(frozen=True)
class AgentRunOnceResult:
    scan_result: WatchScanResult | None
    worker_result: WorkerPipelineResult | None
    blocked_reason: str | None = None
    blocked_message: str | None = None

    @property
    def processed(self) -> bool:
        return self.worker_result is not None and self.worker_result.processed


class AgentRunner:
    """Run the MVP agent once without introducing a service layer or worker pool."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        watcher: FolderWatcher | None = None,
        worker: AgentWorker | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.watcher = watcher or FolderWatcher(self.settings)
        self.worker = worker

    def run_once(self, *, scan_input: bool = True, input_dir: Path | None = None) -> AgentRunOnceResult:
        scan_result = None
        if scan_input:
            with session_scope(self.settings) as session:
                scan_result = self.watcher.scan_once(session, input_dir=input_dir)

        with session_scope(self.settings) as session:
            has_queued_task = bool(ImageTaskRepository().list_by_status(session, TaskStatus.QUEUED))
        if not has_queued_task:
            return AgentRunOnceResult(scan_result=scan_result, worker_result=None)

        lightroom_status = lightroom_classic_status(self.settings)
        if lightroom_status.required and not lightroom_status.running:
            return AgentRunOnceResult(
                scan_result=scan_result,
                worker_result=None,
                blocked_reason=lightroom_status.reason,
                blocked_message=lightroom_status.message,
            )

        worker_result = self._worker().process_next_queued()
        return AgentRunOnceResult(scan_result=scan_result, worker_result=worker_result)

    def process_file(self, file_path: Path) -> WorkerPipelineResult:
        """Queue one explicit file and run the normal one-photo worker pipeline."""

        path = file_path.resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"file does not exist: {path}")
        if not is_supported_photo(path, self.watcher.supported_extensions):
            raise ValueError(f"unsupported file type: {path.suffix.lower()}")

        stability = wait_for_stable_file(
            path,
            required_checks=self.settings.file_stable_checks,
            interval_seconds=self.settings.file_stable_interval_seconds,
            timeout_seconds=self.settings.file_stable_timeout_seconds,
        )
        if not stability.stable:
            raise ValueError(f"file did not stabilize: {stability.reason}")

        source_hash = calculate_file_sha256(path)
        task_repo = ImageTaskRepository()
        event_repo = TaskEventRepository()
        with session_scope(self.settings) as session:
            task = task_repo.get_by_source_path_hash(session, path, source_hash)
            if task is None:
                task = task_repo.create(
                    session,
                    source_path=path,
                    source_hash=source_hash,
                    file_name=path.name,
                    file_ext=path.suffix.lower(),
                    file_size_bytes=stability.size_bytes,
                    status=TaskStatus.QUEUED,
                    current_stage=Stage.WATCH,
                )
                event_repo.create(
                    session,
                    task_id=task.id,
                    event_type=TaskEventType.TASK_CREATED,
                    stage=Stage.WATCH,
                    message="Explicit process command queued one supported file.",
                    payload_json={
                        "loop_name": WATCH_LOOP_NAME,
                        "loop_iteration": 1,
                        "event_type": TaskEventType.TASK_CREATED.value,
                        "from_status": TaskStatus.DETECTED.value,
                        "to_status": TaskStatus.QUEUED.value,
                        "reason": "explicit process command queued file",
                        "source_path": str(path),
                        "source_hash": source_hash,
                        "evidence_artifacts": [],
                    },
                )
            else:
                previous_status = TaskStatus(task.status)
                if previous_status == TaskStatus.PASS:
                    raise ValueError(f"file already has a PASS task: {task.id}")
                if previous_status in {TaskStatus.REVIEW_REQUIRED, TaskStatus.FAILED, TaskStatus.SKIPPED}:
                    task_repo.requeue_for_retry(session, task)
                    event_repo.create(
                        session,
                        task_id=task.id,
                        event_type=TaskEventType.TASK_RETRIED,
                        stage=Stage.RECOVERY,
                        message="Explicit process command requeued an existing task for the same file.",
                        payload_json={
                            "loop_name": WATCH_LOOP_NAME,
                            "loop_iteration": 1,
                            "event_type": TaskEventType.TASK_RETRIED.value,
                            "from_status": previous_status.value,
                            "to_status": TaskStatus.QUEUED.value,
                            "reason": "explicit process command reused existing source_path/source_hash task",
                            "source_path": str(path),
                            "source_hash": source_hash,
                            "retry_count": task.retry_count,
                            "evidence_artifacts": [],
                        },
                    )
                elif previous_status != TaskStatus.QUEUED:
                    event_repo.create(
                        session,
                        task_id=task.id,
                        event_type=TaskEventType.TASK_RETRIED,
                        stage=Stage.RECOVERY,
                        message="Explicit process command reused an existing non-terminal task for the same file.",
                        payload_json={
                            "loop_name": WATCH_LOOP_NAME,
                            "loop_iteration": 1,
                            "event_type": TaskEventType.TASK_RETRIED.value,
                            "from_status": previous_status.value,
                            "to_status": previous_status.value,
                            "reason": "explicit process command reused existing source_path/source_hash task without creating a duplicate",
                            "source_path": str(path),
                            "source_hash": source_hash,
                            "evidence_artifacts": [],
                        },
                    )
            task_id = task.id

        lightroom_status = lightroom_classic_status(self.settings)
        if lightroom_status.required and not lightroom_status.running:
            raise ValueError(lightroom_status.message or "Lightroom Classic is not running.")

        return self._worker().process_task(task_id)

    def retry_task(self, task_id: UUID, *, process_now: bool = False) -> WorkerPipelineResult | None:
        """Requeue a terminal non-PASS task after an explicit operator retry."""

        task_repo = ImageTaskRepository()
        event_repo = TaskEventRepository()
        with session_scope(self.settings) as session:
            task = task_repo.get(session, task_id)
            if task is None:
                raise ValueError(f"image task does not exist: {task_id}")
            previous_status = TaskStatus(task.status)
            if previous_status == TaskStatus.PASS:
                raise ValueError("PASS tasks are not retried automatically")
            if previous_status not in {TaskStatus.REVIEW_REQUIRED, TaskStatus.FAILED, TaskStatus.SKIPPED}:
                raise ValueError(f"task is not in a terminal retryable status: {previous_status.value}")
            source_path = Path(task.source_path)
            if not source_path.exists():
                raise ValueError(f"source file is missing: {source_path}")

            task_repo.requeue_for_retry(session, task)
            event_repo.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_RETRIED,
                stage=Stage.RECOVERY,
                message="Operator explicitly requeued the task for retry.",
                payload_json={
                    "retry_requested": True,
                    "from_status": previous_status.value,
                    "to_status": TaskStatus.QUEUED.value,
                    "retry_count": task.retry_count,
                    "reason": "explicit CLI retry command",
                },
            )

        if process_now:
            lightroom_status = lightroom_classic_status(self.settings)
            if lightroom_status.required and not lightroom_status.running:
                raise ValueError(lightroom_status.message or "Lightroom Classic is not running.")
            return self._worker().process_task(task_id)
        return None

    def _worker(self) -> AgentWorker:
        if self.worker is None:
            self.worker = AgentWorker(settings=self.settings)
        return self.worker


def run_once(*, settings: Settings | None = None, scan_input: bool = True, input_dir: Path | None = None) -> AgentRunOnceResult:
    return AgentRunner(settings=settings).run_once(scan_input=scan_input, input_dir=input_dir)
