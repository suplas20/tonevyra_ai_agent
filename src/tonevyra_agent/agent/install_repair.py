"""Bounded repair for tasks produced by legacy mock-model installers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import Stage, TaskEventType, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskEventRepository


TERMINAL_REPAIR_STATUSES = (
    TaskStatus.PASS,
    TaskStatus.REVIEW_REQUIRED,
    TaskStatus.FAILED,
)


@dataclass(frozen=True)
class LegacyModelRepairResult:
    enabled: bool
    scanned_count: int
    requeued_task_ids: list[str]
    skipped_missing_source: int
    skipped_retry_limit: int

    def to_dict(self) -> dict:
        return {
            "schema_version": "tonevyra.install_repair.legacy_model.v1",
            **asdict(self),
        }


def requeue_legacy_mock_tasks(
    settings: Settings | None = None,
    *,
    max_tasks: int = 100,
    max_retry_count: int = 3,
) -> LegacyModelRepairResult:
    """Requeue bounded terminal tasks whose persisted vision backend was mock."""

    config = settings or get_settings()
    if config.vision_backend.lower() == "mock":
        return LegacyModelRepairResult(False, 0, [], 0, 0)

    task_repo = ImageTaskRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()
    input_root = config.project_path(config.input_dir).resolve()
    requeued: list[str] = []
    scanned = 0
    skipped_missing = 0
    skipped_limit = 0

    with session_scope(config) as session:
        candidates = []
        for status in TERMINAL_REPAIR_STATUSES:
            candidates.extend(task_repo.list_by_status(session, status))
        candidates.sort(key=lambda task: (task.updated_at, task.created_at), reverse=True)

        for task in candidates:
            if scanned >= max_tasks:
                break
            scanned += 1
            vision_result = next(
                (result for result in stage_repo.list_for_task(session, task.id) if result.stage == Stage.VISION.value),
                None,
            )
            backend = str((vision_result.summary_json or {}).get("model_backend", "")).lower() if vision_result else ""
            if backend != "mock":
                continue
            if task.retry_count >= max_retry_count:
                skipped_limit += 1
                continue

            source_path = Path(task.source_path).resolve()
            if not source_path.is_file() or not source_path.is_relative_to(input_root):
                skipped_missing += 1
                continue

            previous_status = task.status
            previous_error_code = task.error_code
            task_repo.requeue_for_retry(session, task)
            event_repo.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_RETRIED,
                stage=Stage.RECOVERY,
                message="Installer repair requeued a task produced by the legacy mock vision backend.",
                payload_json={
                    "loop_name": "installer_repair_loop",
                    "from_status": previous_status,
                    "to_status": TaskStatus.QUEUED.value,
                    "reason": "replace persisted mock vision result with configured local model analysis",
                    "previous_model_backend": "mock",
                    "configured_model_backend": config.vision_backend,
                    "previous_error_code": previous_error_code,
                    "retry_count": task.retry_count,
                    "retry_limit": max_retry_count,
                },
            )
            requeued.append(str(task.id))

    return LegacyModelRepairResult(True, scanned, requeued, skipped_missing, skipped_limit)
