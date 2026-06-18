"""Crash recovery loop for unfinished Tonevyra AI tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, QualityDecision, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.models import ImageTask, TaskArtifact
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    QualityResultRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)
from tonevyra_agent.lightroom.bridge import LightroomBridge
from tonevyra_agent.quality.analyzer import QualityGate
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


RECOVERY_LOOP_NAME = "recovery_loop"
RECOVERABLE_STATUSES: tuple[TaskStatus, ...] = (
    TaskStatus.DETECTED,
    TaskStatus.STABILIZING,
    TaskStatus.QUEUED,
    TaskStatus.ANALYZING,
    TaskStatus.ANALYSIS_DONE,
    TaskStatus.CORRECTION_PLANNED,
    TaskStatus.LIGHTROOM_REQUESTED,
    TaskStatus.LIGHTROOM_PROCESSING,
    TaskStatus.EXPORT_DONE,
    TaskStatus.QUALITY_CHECK,
)
TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.PASS,
        TaskStatus.REVIEW_REQUIRED,
        TaskStatus.FAILED,
        TaskStatus.SKIPPED,
    }
)


@dataclass(frozen=True)
class RecoveryTaskResult:
    task_id: UUID
    previous_status: TaskStatus
    decision: str
    final_status: TaskStatus
    recovery_artifact: ArtifactRef | None
    reason: str
    error_code: ErrorCode | None = None


@dataclass(frozen=True)
class RecoveryRunResult:
    inspected_count: int
    recovered_count: int
    failed_count: int
    results: tuple[RecoveryTaskResult, ...]


@dataclass
class ArtifactEvidence:
    artifact_type: ArtifactType
    row: TaskArtifact | None = None
    exists: bool = False
    checksum_valid: bool = False
    json_valid: bool | None = None
    path: str | None = None
    sha256: str | None = None
    missing_reason: str | None = None

    @property
    def valid(self) -> bool:
        if self.row is None or not self.exists or not self.checksum_valid:
            return False
        return self.json_valid is not False

    def as_payload(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type.value,
            "artifact_path": self.path,
            "row_exists": self.row is not None,
            "file_exists": self.exists,
            "checksum_valid": self.checksum_valid,
            "json_valid": self.json_valid,
            "sha256": self.sha256,
            "missing_reason": self.missing_reason,
        }


@dataclass
class RecoveryDecision:
    decision: str
    reason: str
    previous_status: TaskStatus
    previous_stage: str | None
    resume_from_stage: Stage | None = None
    target_status: TaskStatus | None = None
    target_stage: Stage | None = None
    error_code: ErrorCode | None = None
    action: str = "no_action"
    response_path: Path | None = None
    export_artifact: TaskArtifact | None = None
    export_path: Path | None = None
    quality_decision: QualityDecision | None = None
    quality_overall_score: float | None = None
    evidence_checked: list[dict[str, Any]] = field(default_factory=list)
    missing_evidence: list[dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)

    def payload(self, task_id: UUID) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "task_id": str(task_id),
            "previous_status": self.previous_status.value,
            "previous_stage": self.previous_stage,
            "decision": self.decision,
            "resume_from_stage": self.resume_from_stage.value if self.resume_from_stage else None,
            "target_status": self.target_status.value if self.target_status else None,
            "target_stage": self.target_stage.value if self.target_stage else None,
            "reason": self.reason,
            "evidence_checked": self.evidence_checked,
            "missing_evidence": self.missing_evidence,
            "artifact_refs": self.artifact_refs,
            "error_code": self.error_code.value if self.error_code else None,
        }


class RecoveryManager:
    """Recover unfinished tasks using durable DB and artifact evidence."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage: ArtifactStorage | None = None,
        task_repository: ImageTaskRepository | None = None,
        artifact_repository: TaskArtifactRepository | None = None,
        event_repository: TaskEventRepository | None = None,
        stage_repository: StageResultRepository | None = None,
        quality_repository: QualityResultRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or ArtifactStorage(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.artifact_repository = artifact_repository or TaskArtifactRepository()
        self.event_repository = event_repository or TaskEventRepository()
        self.stage_repository = stage_repository or StageResultRepository()
        self.quality_repository = quality_repository or QualityResultRepository()
        self.lightroom_bridge = LightroomBridge(settings=self.settings, storage=self.storage)
        self.quality_gate = QualityGate(settings=self.settings, storage=self.storage)

    def recover_all(self) -> RecoveryRunResult:
        task_ids: list[UUID] = []
        with session_scope(self.settings) as session:
            for status in RECOVERABLE_STATUSES:
                task_ids.extend(task.id for task in self.task_repository.list_by_status(session, status))

        results = tuple(self.recover_task(task_id) for task_id in task_ids)
        return RecoveryRunResult(
            inspected_count=len(task_ids),
            recovered_count=sum(1 for result in results if result.decision in {"resume", "requeue"}),
            failed_count=sum(1 for result in results if result.final_status == TaskStatus.FAILED),
            results=results,
        )

    def recover_task(self, task_id: UUID) -> RecoveryTaskResult:
        started_at = datetime.utcnow()
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            previous_status = TaskStatus(task.status)
            previous_stage = task.current_stage

            if previous_status in TERMINAL_STATUSES:
                return RecoveryTaskResult(
                    task_id=task.id,
                    previous_status=previous_status,
                    decision="no_action",
                    final_status=previous_status,
                    recovery_artifact=None,
                    reason="terminal task was not resumed automatically",
                )

            decision = self._decide(session, task)
            decision_artifact = self.storage.save_json(
                session,
                task_id=task.id,
                artifact_type=ArtifactType.RECOVERY_DECISION,
                name="recovery_decision.json",
                data=decision.payload(task.id),
            )
            self._apply_decision(session, task, decision)
            finished_at = datetime.utcnow()
            final_status = TaskStatus(task.status)

            self.stage_repository.create(
                session,
                task_id=task.id,
                stage=Stage.RECOVERY,
                stage_status=StageStatus.FAILED if final_status == TaskStatus.FAILED else StageStatus.SUCCEEDED,
                summary_json={
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "resume_from_stage": decision.resume_from_stage.value if decision.resume_from_stage else None,
                    "target_status": decision.target_status.value if decision.target_status else final_status.value,
                    "recovery_decision_artifact": _artifact_summary(decision_artifact),
                },
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
            )
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.RECOVERY_RESUMED,
                stage=Stage.RECOVERY,
                message="Recovery loop inspected durable evidence and applied a safe action.",
                payload_json={
                    "loop_name": RECOVERY_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.RECOVERY_RESUMED.value,
                    "from_status": previous_status.value,
                    "to_status": final_status.value,
                    "reason": decision.reason,
                    "recovery_action": decision.action,
                    "evidence_checked": decision.evidence_checked,
                    "missing_evidence": decision.missing_evidence,
                    "artifact_refs": decision.artifact_refs,
                    "error_code": decision.error_code.value if decision.error_code else None,
                    "evidence_artifacts": [_artifact_summary(decision_artifact)],
                },
            )
            return RecoveryTaskResult(
                task_id=task.id,
                previous_status=previous_status,
                decision=decision.decision,
                final_status=final_status,
                recovery_artifact=decision_artifact,
                reason=decision.reason,
                error_code=decision.error_code,
            )

    def _decide(self, session: Session, task: ImageTask) -> RecoveryDecision:
        status = TaskStatus(task.status)
        previous_stage = task.current_stage

        if status in {TaskStatus.DETECTED, TaskStatus.STABILIZING, TaskStatus.QUEUED}:
            if _source_path(task.source_path).exists():
                return self._decision(
                    task,
                    "requeue",
                    "source file exists; task can restart from metadata",
                    resume_from_stage=Stage.METADATA,
                    target_status=TaskStatus.QUEUED,
                    target_stage=Stage.WATCH,
                    action="set_status",
                )
            return self._decision(
                task,
                "fail",
                "source file is missing during recovery",
                error_code=ErrorCode.FILE_NOT_STABLE,
                target_status=TaskStatus.FAILED,
                target_stage=Stage.WATCH,
                action="fail",
            )

        if status == TaskStatus.ANALYZING:
            vision = self._artifact_evidence(session, task.id, ArtifactType.VISION_STRUCTURED, require_json=True)
            decision = self._decision_from_vision(task, vision, previous_stage)
            return decision

        if status == TaskStatus.ANALYSIS_DONE:
            vision = self._artifact_evidence(session, task.id, ArtifactType.VISION_STRUCTURED, require_json=True)
            if vision.valid:
                return self._decision(
                    task,
                    "resume",
                    "vision_structured artifact is valid; resume from correction planning",
                    resume_from_stage=Stage.CORRECTION_PLAN,
                    target_status=TaskStatus.ANALYSIS_DONE,
                    target_stage=Stage.VISION,
                    action="set_status",
                    evidence=[vision],
                )
            return self._decision(
                task,
                "resume",
                "vision evidence is incomplete; resume from vision analysis",
                resume_from_stage=Stage.VISION,
                target_status=TaskStatus.ANALYZING,
                target_stage=Stage.VISION,
                action="set_status",
                evidence=[vision],
            )

        if status == TaskStatus.CORRECTION_PLANNED:
            plan = self._artifact_evidence(session, task.id, ArtifactType.CORRECTION_PLAN, require_json=True)
            if plan.valid:
                return self._decision(
                    task,
                    "resume",
                    "correction_plan artifact is valid; resume from Lightroom bridge",
                    resume_from_stage=Stage.LIGHTROOM,
                    target_status=TaskStatus.CORRECTION_PLANNED,
                    target_stage=Stage.CORRECTION_PLAN,
                    action="set_status",
                    evidence=[plan],
                )
            return self._decision(
                task,
                "resume",
                "correction_plan evidence is incomplete; resume from correction planning",
                resume_from_stage=Stage.CORRECTION_PLAN,
                target_status=TaskStatus.ANALYSIS_DONE,
                target_stage=Stage.VISION,
                action="set_status",
                evidence=[plan],
            )

        if status in {TaskStatus.LIGHTROOM_REQUESTED, TaskStatus.LIGHTROOM_PROCESSING}:
            return self._decide_lightroom(session, task)

        if status == TaskStatus.EXPORT_DONE:
            export_artifact, export_path, export_evidence = self._export_evidence(session, task)
            if export_artifact is not None or export_path is not None:
                return self._decision(
                    task,
                    "resume",
                    "export evidence exists; resume from quality gate",
                    resume_from_stage=Stage.QUALITY,
                    target_status=TaskStatus.QUALITY_CHECK,
                    target_stage=Stage.QUALITY,
                    action="run_quality",
                    export_artifact=export_artifact,
                    export_path=export_path,
                    evidence=export_evidence,
                )
            return self._decision(
                task,
                "fail",
                "export evidence is missing",
                error_code=ErrorCode.EXPORT_FILE_MISSING,
                target_status=TaskStatus.FAILED,
                target_stage=Stage.EXPORT,
                action="fail",
                evidence=export_evidence,
            )

        if status == TaskStatus.QUALITY_CHECK:
            return self._decide_quality_check(session, task)

        return self._decision(task, "no_action", "status is not recoverable", action="no_action")

    def _decision_from_vision(
        self,
        task: ImageTask,
        vision: ArtifactEvidence,
        previous_stage: str | None,
    ) -> RecoveryDecision:
        if vision.valid:
            return self._decision(
                task,
                "resume",
                "vision_structured artifact is valid; resume from correction planning",
                resume_from_stage=Stage.CORRECTION_PLAN,
                target_status=TaskStatus.ANALYSIS_DONE,
                target_stage=Stage.VISION,
                action="set_status",
                evidence=[vision],
            )

        target_stage = Stage.VISION if previous_stage == Stage.VISION.value else Stage.METADATA
        return self._decision(
            task,
            "resume",
            "vision_structured artifact is missing or invalid; resume from vision analysis",
            resume_from_stage=Stage.VISION,
            target_status=TaskStatus.ANALYZING,
            target_stage=target_stage,
            action="set_status",
            evidence=[vision],
        )

    def _decide_lightroom(self, session: Session, task: ImageTask) -> RecoveryDecision:
        request = self._artifact_evidence(session, task.id, ArtifactType.LIGHTROOM_REQUEST, require_json=True)
        if self.settings.lightroom_backend == "lightroom":
            apply_result_path = self.lightroom_bridge.apply_result_path(str(task.id))
            apply_result_evidence = _file_evidence("lightroom_apply_result_file", apply_result_path)
            evidence = [request.as_payload(), apply_result_evidence]
            if apply_result_path.exists():
                return self._decision(
                    task,
                    "resume",
                    "Lightroom apply result exists; ingest apply-adapter result",
                    resume_from_stage=Stage.LIGHTROOM,
                    target_status=TaskStatus.LIGHTROOM_PROCESSING,
                    target_stage=Stage.LIGHTROOM,
                    action="ingest_response",
                    response_path=apply_result_path,
                    raw_evidence=evidence,
                )
            if request.valid:
                return self._decision(
                    task,
                    "no_action",
                    "Lightroom apply request exists; waiting for Lightroom apply-adapter result",
                    target_status=TaskStatus.LIGHTROOM_REQUESTED,
                    target_stage=Stage.LIGHTROOM,
                    action="set_status",
                    raw_evidence=evidence,
                )
            return self._decision(
                task,
                "fail",
                "Lightroom apply request evidence is missing or invalid",
                error_code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                target_status=TaskStatus.FAILED,
                target_stage=Stage.LIGHTROOM,
                action="fail",
                raw_evidence=evidence,
            )

        response_path = self.lightroom_bridge.response_path(str(task.id))
        response_evidence = _file_evidence("lightroom_response_file", response_path)
        export_path = self._export_path_from_response(response_path)
        export_file_evidence = _file_evidence("lightroom_export_file", export_path) if export_path else None

        evidence = [request.as_payload(), response_evidence]
        if export_file_evidence:
            evidence.append(export_file_evidence)

        if response_path.exists() and export_path is not None and export_path.exists():
            return self._decision(
                task,
                "resume",
                "Lightroom response and export exist; ingest response and resume quality gate",
                resume_from_stage=Stage.QUALITY,
                target_status=TaskStatus.QUALITY_CHECK,
                target_stage=Stage.QUALITY,
                action="ingest_response_then_quality",
                response_path=response_path,
                export_path=export_path,
                raw_evidence=evidence,
            )

        if request.valid:
            return self._decision(
                task,
                "fail",
                "Lightroom request exists but response/export evidence is missing",
                error_code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                target_status=TaskStatus.FAILED,
                target_stage=Stage.LIGHTROOM,
                action="fail",
                raw_evidence=evidence,
            )

        plan = self._artifact_evidence(session, task.id, ArtifactType.CORRECTION_PLAN, require_json=True)
        target_status = TaskStatus.CORRECTION_PLANNED if plan.valid else TaskStatus.ANALYSIS_DONE
        target_stage = Stage.CORRECTION_PLAN if plan.valid else Stage.VISION
        return self._decision(
            task,
            "resume",
            "Lightroom request is missing; resume from the safest pre-Lightroom stage",
            resume_from_stage=Stage.LIGHTROOM if plan.valid else Stage.CORRECTION_PLAN,
            target_status=target_status,
            target_stage=target_stage,
            action="set_status",
            evidence=[request, plan],
        )

    def _decide_quality_check(self, session: Session, task: ImageTask) -> RecoveryDecision:
        quality_detail = self._artifact_evidence(session, task.id, ArtifactType.QUALITY_DETAIL, require_json=True)
        quality_results = self.quality_repository.list_for_task(session, task.id)
        quality_evidence = {
            "kind": "quality_results",
            "row_count": len(quality_results),
            "latest_decision": quality_results[-1].decision if quality_results else None,
        }

        if quality_detail.valid and quality_results:
            latest = quality_results[-1]
            return self._decision(
                task,
                "resume",
                "quality evidence exists; finalize task from persisted quality decision",
                resume_from_stage=Stage.QUALITY,
                target_status=TaskStatus(latest.decision),
                target_stage=Stage.QUALITY,
                action="finalize_quality",
                quality_decision=QualityDecision(latest.decision),
                quality_overall_score=float(latest.overall_score),
                evidence=[quality_detail],
                raw_evidence=[quality_evidence],
            )

        export_artifact, export_path, export_evidence = self._export_evidence(session, task)
        if export_artifact is not None or export_path is not None:
            return self._decision(
                task,
                "resume",
                "quality result is missing; rerun quality gate from export evidence",
                resume_from_stage=Stage.QUALITY,
                target_status=TaskStatus.QUALITY_CHECK,
                target_stage=Stage.QUALITY,
                action="run_quality",
                export_artifact=export_artifact,
                export_path=export_path,
                evidence=[quality_detail, *export_evidence],
                raw_evidence=[quality_evidence],
            )

        return self._decision(
            task,
            "fail",
            "quality and export evidence are missing",
            error_code=ErrorCode.EXPORT_FILE_MISSING,
            target_status=TaskStatus.FAILED,
            target_stage=Stage.EXPORT,
            action="fail",
            evidence=[quality_detail, *export_evidence],
            raw_evidence=[quality_evidence],
        )

    def _decision(
        self,
        task: ImageTask,
        decision: str,
        reason: str,
        *,
        resume_from_stage: Stage | None = None,
        target_status: TaskStatus | None = None,
        target_stage: Stage | None = None,
        error_code: ErrorCode | None = None,
        action: str,
        response_path: Path | None = None,
        export_artifact: TaskArtifact | None = None,
        export_path: Path | None = None,
        quality_decision: QualityDecision | None = None,
        quality_overall_score: float | None = None,
        evidence: list[ArtifactEvidence] | None = None,
        raw_evidence: list[dict[str, Any]] | None = None,
    ) -> RecoveryDecision:
        checked = raw_evidence[:] if raw_evidence else []
        missing: list[dict[str, Any]] = []
        artifact_refs: list[dict[str, Any]] = []

        for item in evidence or []:
            payload = item.as_payload()
            checked.append(payload)
            if not item.valid:
                missing.append(payload)
            elif item.row is not None:
                artifact_refs.append(_db_artifact_summary(item.row))

        if export_artifact is not None:
            artifact_refs.append(_db_artifact_summary(export_artifact))

        return RecoveryDecision(
            decision=decision,
            reason=reason,
            previous_status=TaskStatus(task.status),
            previous_stage=task.current_stage,
            resume_from_stage=resume_from_stage,
            target_status=target_status,
            target_stage=target_stage,
            error_code=error_code,
            action=action,
            response_path=response_path,
            export_artifact=export_artifact,
            export_path=export_path,
            quality_decision=quality_decision,
            quality_overall_score=quality_overall_score,
            evidence_checked=checked,
            missing_evidence=missing,
            artifact_refs=artifact_refs,
        )

    def _apply_decision(self, session: Session, task: ImageTask, decision: RecoveryDecision) -> None:
        if decision.action == "set_status" and decision.target_status is not None:
            self.task_repository.update_status(session, task, status=decision.target_status, current_stage=decision.target_stage)
            return

        if decision.action == "fail" and decision.error_code is not None and decision.target_stage is not None:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=decision.error_code,
                error_message=decision.reason,
                failed_stage=decision.target_stage,
            )
            return

        if decision.action == "ingest_response_then_quality" and decision.response_path is not None:
            response = self.lightroom_bridge.ingest_response(session, task=task, response_path=decision.response_path)
            if response.export_artifact is None:
                return
            self.task_repository.update_status(session, task, status=TaskStatus.QUALITY_CHECK, current_stage=Stage.QUALITY)
            self.quality_gate.evaluate_export(session, task=task, export_artifact=response.export_artifact)
            return

        if decision.action == "ingest_response" and decision.response_path is not None:
            self.lightroom_bridge.ingest_response(session, task=task, response_path=decision.response_path)
            return

        if decision.action == "run_quality":
            self.task_repository.update_status(session, task, status=TaskStatus.QUALITY_CHECK, current_stage=Stage.QUALITY)
            self.quality_gate.evaluate_export(
                session,
                task=task,
                export_artifact=self.storage._to_ref(decision.export_artifact) if decision.export_artifact else None,
                export_path=decision.export_path,
            )
            return

        if decision.action == "finalize_quality" and decision.quality_decision is not None:
            self.task_repository.finalize_quality(
                session,
                task,
                decision=decision.quality_decision,
                overall_score=decision.quality_overall_score or 0,
            )

    def _artifact_evidence(
        self,
        session: Session,
        task_id: UUID,
        artifact_type: ArtifactType,
        *,
        require_json: bool = False,
    ) -> ArtifactEvidence:
        row = self.artifact_repository.get_for_task_type_version(session, task_id=task_id, artifact_type=artifact_type)
        if row is None:
            return ArtifactEvidence(artifact_type=artifact_type, missing_reason="artifact row missing")

        evidence = ArtifactEvidence(
            artifact_type=artifact_type,
            row=row,
            path=row.artifact_path,
            sha256=row.sha256,
        )
        try:
            evidence.exists = self.storage.exists(row)
            evidence.checksum_valid = self.storage.verify_checksum(row) if row.sha256 else evidence.exists
            if require_json and evidence.exists and evidence.checksum_valid:
                self.storage.load_json(row)
                evidence.json_valid = True
            elif require_json:
                evidence.json_valid = False
        except Exception as exc:
            evidence.missing_reason = str(exc)
            if require_json:
                evidence.json_valid = False
        if not evidence.exists:
            evidence.missing_reason = "artifact file missing"
        elif not evidence.checksum_valid:
            evidence.missing_reason = "artifact checksum mismatch"
        return evidence

    def _export_evidence(
        self,
        session: Session,
        task: ImageTask,
    ) -> tuple[TaskArtifact | None, Path | None, list[ArtifactEvidence]]:
        export = self._artifact_evidence(session, task.id, ArtifactType.EXPORTED_IMAGE, require_json=False)
        if export.valid and export.row is not None:
            return export.row, None, [export]

        response_path = self.lightroom_bridge.response_path(str(task.id))
        export_path = self._export_path_from_response(response_path)
        if export_path is not None and export_path.exists():
            return None, export_path, [export]

        fallback_path = self.settings.project_path(self.settings.output_dir) / "temp" / f"{task.id}.jpg"
        if fallback_path.exists():
            return None, fallback_path.resolve(), [export]

        return None, None, [export]

    def _export_path_from_response(self, response_path: Path) -> Path | None:
        if not response_path.exists():
            return None
        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        export_path = payload.get("export_path")
        if not export_path:
            return None
        return _source_path(export_path)

    def _require_task(self, session: Session, task_id: UUID) -> ImageTask:
        task = self.task_repository.get(session, task_id)
        if task is None:
            raise RuntimeError(f"image task does not exist: {task_id}")
        return task


def recover_all(*, settings: Settings | None = None) -> RecoveryRunResult:
    return RecoveryManager(settings=settings).recover_all()


def recover_task(task_id: UUID, *, settings: Settings | None = None) -> RecoveryTaskResult:
    return RecoveryManager(settings=settings).recover_task(task_id)


def _source_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _file_evidence(kind: str, path: Path | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path.resolve()) if path else None,
        "file_exists": path.exists() if path else False,
    }


def _artifact_summary(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _db_artifact_summary(artifact: TaskArtifact) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.artifact_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
