"""Database/artifact adapter for the T-032 remote Planner API stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.schemas import CorrectionPlan
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskEventRepository
from tonevyra_agent.planner_api.client import PlannerApiClient
from tonevyra_agent.planner_api.contracts import (
    build_planner_request,
    csv_set,
    response_to_correction_plan,
    validate_request_digest,
)
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage
from tonevyra_agent.vision.schemas import VisionAnalysisResult


PROCESSING_LOOP_NAME = "processing_loop"
PLANNER_REQUEST_ARTIFACT_VERSION = 32
PLANNER_RESPONSE_ARTIFACT_VERSION = 33
PLANNER_ATTEMPTS_ARTIFACT_VERSION = 34


@dataclass(frozen=True)
class RemotePlannerEvidence:
    request_artifact: ArtifactRef
    response_artifact: ArtifactRef | None
    attempts_artifact: ArtifactRef | None


@dataclass(frozen=True)
class RemoteCorrectionPlannerResult:
    plan: CorrectionPlan
    artifact: ArtifactRef
    comparison_artifact: ArtifactRef | None = None


class RemoteCorrectionPlanner:
    """Create a CorrectionPlan through the authenticated remote Planner API."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage: ArtifactStorage | None = None,
        client: PlannerApiClient | None = None,
        task_repository: ImageTaskRepository | None = None,
        stage_repository: StageResultRepository | None = None,
        event_repository: TaskEventRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or ArtifactStorage(self.settings)
        self.client = client or PlannerApiClient(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.stage_repository = stage_repository or StageResultRepository()
        self.event_repository = event_repository or TaskEventRepository()

    def plan_from_artifact(
        self,
        session: Session,
        *,
        task: ImageTask,
        vision_artifact: ArtifactRef,
        metadata_artifact: ArtifactRef,
    ) -> RemoteCorrectionPlannerResult:
        started_at = datetime.utcnow()
        from_status = task.status
        request_id = str(uuid4())
        idempotency_key = f"task:{task.id}:planner:{vision_artifact.sha256[:16]}"

        analysis_payload = self.storage.load_json(vision_artifact)
        metadata_payload = self.storage.load_json(metadata_artifact)
        analysis = VisionAnalysisResult.model_validate(analysis_payload)
        request = build_planner_request(
            request_id=request_id,
            analysis=analysis,
            metadata=metadata_payload,
            settings=self.settings,
        )
        request_payload = request.model_dump(mode="json")
        validate_request_digest(request_payload)

        request_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="planner_request.json",
            data={
                "schema_version": "tonevyra.planner_api_request_artifact.v1",
                "request": request_payload,
                "idempotency_key": idempotency_key,
                "authorization_header_stored": False,
            },
            version=PLANNER_REQUEST_ARTIFACT_VERSION,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type="PLANNER_API_REQUESTED",
            stage=Stage.CORRECTION_PLAN,
            message="Persisted sanitized Planner API request evidence before network send.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "event_type": "PLANNER_API_REQUESTED",
                "from_status": from_status,
                "to_status": task.status,
                "request_id": request_id,
                "idempotency_key": idempotency_key,
                "input_digest": request.input_digest,
                "evidence_artifacts": [_artifact_summary(request_artifact)],
            },
        )
        session.flush()

        try:
            result = self.client.create_plan(request=request, idempotency_key=idempotency_key)
        except TonevyraError as exc:
            self._persist_attempts(
                session,
                task=task,
                request_id=request_id,
                input_digest=request.input_digest,
                attempts=[attempt.to_json() for attempt in self.client.last_attempts],
                exhausted=exc.code == ErrorCode.PLANNER_API_RETRY_EXHAUSTED,
            )
            raise

        response_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="planner_response.json",
            data=result.response_payload,
            version=PLANNER_RESPONSE_ARTIFACT_VERSION,
        )
        attempts_artifact = self._persist_attempts(
            session,
            task=task,
            request_id=request_id,
            input_digest=request.input_digest,
            attempts=[attempt.to_json() for attempt in result.attempts],
            exhausted=False,
        )
        plan = response_to_correction_plan(
            request=request,
            response_payload=result.response_payload,
            supported_planner_versions=csv_set(self.settings.planner_api_supported_planner_versions),
            supported_policy_versions=csv_set(self.settings.planner_api_supported_policy_versions),
        )
        correction_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="correction_plan.json",
            data=plan.model_dump(mode="json"),
        )

        finished_at = datetime.utcnow()
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.CORRECTION_PLAN,
            stage_status=StageStatus.SUCCEEDED,
            summary_json={
                **plan.summary(),
                "planner_mode": "remote_api",
                "planner_request_artifact": _artifact_summary(request_artifact),
                "planner_response_artifact": _artifact_summary(response_artifact),
                "planner_attempts_artifact": _artifact_summary(attempts_artifact),
                "correction_plan_artifact": _artifact_summary(correction_artifact),
                "vision_structured_artifact": _artifact_summary(vision_artifact),
                "metadata_artifact": _artifact_summary(metadata_artifact),
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.CORRECTION_PLANNED,
            current_stage=Stage.CORRECTION_PLAN,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.CORRECTION_PLANNED,
            stage=Stage.CORRECTION_PLAN,
            message="Remote Planner API returned a validated Lightroom adjustment plan.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "event_type": TaskEventType.CORRECTION_PLANNED.value,
                "from_status": from_status,
                "to_status": TaskStatus.CORRECTION_PLANNED.value,
                "request_id": request_id,
                "input_digest": request.input_digest,
                "plan_digest": plan.source.get("plan_digest"),
                "requires_review": plan.requires_review,
                "evidence_artifacts": [
                    _artifact_summary(request_artifact),
                    _artifact_summary(response_artifact),
                    _artifact_summary(correction_artifact),
                ],
            },
        )
        return RemoteCorrectionPlannerResult(plan=plan, artifact=correction_artifact, comparison_artifact=response_artifact)

    def _persist_attempts(
        self,
        session: Session,
        *,
        task: ImageTask,
        request_id: str,
        input_digest: str,
        attempts: list[dict[str, object]],
        exhausted: bool,
    ) -> ArtifactRef:
        artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="planner_api_attempts.json",
            data={
                "schema_version": "tonevyra.planner_api_attempts.v1",
                "request_id": request_id,
                "input_digest": input_digest,
                "attempts": attempts,
                "exhausted": exhausted,
                "local_fallback_used": False,
            },
            version=PLANNER_ATTEMPTS_ARTIFACT_VERSION,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_RETRIED if attempts else "PLANNER_API_ATTEMPT_LOGGED",
            stage=Stage.CORRECTION_PLAN,
            message="Planner API attempt evidence persisted.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "event_type": "PLANNER_API_ATTEMPT_LOGGED",
                "from_status": task.status,
                "to_status": task.status,
                "request_id": request_id,
                "attempt_count": len(attempts),
                "retry_exhausted": exhausted,
                "local_fallback_used": False,
                "evidence_artifacts": [_artifact_summary(artifact)],
            },
        )
        return artifact


def _artifact_summary(artifact: ArtifactRef | None) -> dict[str, object]:
    if artifact is None:
        return {}
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
