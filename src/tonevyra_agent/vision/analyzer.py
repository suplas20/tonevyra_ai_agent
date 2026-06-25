"""Vision analysis orchestration and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    StageResultRepository,
    TaskEventRepository,
)
from tonevyra_agent.learning.recipe_calibration import build_recipe_model_guidance
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage
from tonevyra_agent.vision.model import VisionModelBackend, create_vision_backend
from tonevyra_agent.vision.schemas import VisionAnalysisResult


PROCESSING_LOOP_NAME = "processing_loop"


@dataclass(frozen=True)
class VisionAnalysisArtifacts:
    prompt_artifact: ArtifactRef
    raw_artifact: ArtifactRef
    structured_artifact: ArtifactRef
    result: VisionAnalysisResult


class VisionAnalyzer:
    """Run a configured vision backend and persist validated outputs."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        backend: VisionModelBackend | None = None,
        storage: ArtifactStorage | None = None,
        task_repository: ImageTaskRepository | None = None,
        stage_repository: StageResultRepository | None = None,
        event_repository: TaskEventRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.backend = backend or create_vision_backend(self.settings)
        self.storage = storage or ArtifactStorage(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.stage_repository = stage_repository or StageResultRepository()
        self.event_repository = event_repository or TaskEventRepository()

    def analyze(
        self,
        session: Session,
        *,
        task: ImageTask,
        preview_artifact: ArtifactRef,
        metadata_artifact: ArtifactRef,
    ) -> VisionAnalysisArtifacts:
        started_at = datetime.utcnow()
        from_status = task.status
        self.task_repository.update_status(session, task, status=TaskStatus.ANALYZING, current_stage=Stage.VISION)

        metadata = self.storage.load_json(metadata_artifact)
        prompt = build_vision_prompt(metadata=metadata)
        prompt_ref = self.storage.save_text(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.VISION_PROMPT,
            name="vision_prompt.txt",
            text=prompt,
        )

        raw_payload = self.backend.analyze(
            preview_path=preview_artifact.absolute_path,
            metadata=metadata,
            prompt=prompt,
        )
        raw_ref = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.VISION_RAW_RESPONSE,
            name="vision_raw_response.json",
            data=raw_payload,
        )

        try:
            result = VisionAnalysisResult.model_validate(raw_payload)
        except ValidationError as exc:
            self._record_invalid_output(
                session,
                task=task,
                started_at=started_at,
                raw_artifact=raw_ref,
                prompt_artifact=prompt_ref,
                error_message=str(exc),
                from_status=from_status,
            )
            raise TonevyraError(
                code=ErrorCode.MODEL_OUTPUT_INVALID,
                message="Vision backend output did not match the required schema.",
                failed_stage=Stage.VISION.value,
            ) from exc

        if result.confidence < self.settings.vision_review_confidence_threshold:
            result.requires_review = True

        structured_ref = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.VISION_STRUCTURED,
            name="vision_structured.json",
            data=result.model_dump(mode="json"),
        )

        finished_at = datetime.utcnow()
        stage_summary = {
            **result.summary(),
            "prompt_artifact": _artifact_summary(prompt_ref),
            "raw_artifact": _artifact_summary(raw_ref),
            "structured_artifact": _artifact_summary(structured_ref),
        }
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.VISION,
            stage_status=StageStatus.SUCCEEDED,
            summary_json=stage_summary,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.ANALYSIS_DONE,
            current_stage=Stage.VISION,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.VISION_COMPLETED,
            stage=Stage.VISION,
            message="Vision analysis completed with validated structured output.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.VISION_COMPLETED.value,
                "from_status": from_status,
                "to_status": TaskStatus.ANALYSIS_DONE.value,
                "reason": "vision_structured artifact saved",
                "requires_review": result.requires_review,
                "evidence_artifacts": [
                    _artifact_summary(prompt_ref),
                    _artifact_summary(raw_ref),
                    _artifact_summary(structured_ref),
                ],
            },
        )
        return VisionAnalysisArtifacts(
            prompt_artifact=prompt_ref,
            raw_artifact=raw_ref,
            structured_artifact=structured_ref,
            result=result,
        )

    def _record_invalid_output(
        self,
        session: Session,
        *,
        task: ImageTask,
        started_at: datetime,
        raw_artifact: ArtifactRef,
        prompt_artifact: ArtifactRef,
        error_message: str,
        from_status: str,
    ) -> None:
        finished_at = datetime.utcnow()
        summary = {
            "error_code": ErrorCode.MODEL_OUTPUT_INVALID.value,
            "error_message": error_message,
            "prompt_artifact": _artifact_summary(prompt_artifact),
            "raw_artifact": _artifact_summary(raw_artifact),
        }
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.VISION,
            stage_status=StageStatus.FAILED,
            summary_json=summary,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.mark_failed(
            session,
            task,
            error_code=ErrorCode.MODEL_OUTPUT_INVALID,
            error_message="Vision backend output did not match the required schema.",
            failed_stage=Stage.VISION,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_FAILED,
            stage=Stage.VISION,
            message="Vision output schema validation failed.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.TASK_FAILED.value,
                "from_status": from_status,
                "to_status": TaskStatus.FAILED.value,
                "reason": ErrorCode.MODEL_OUTPUT_INVALID.value,
                "evidence_artifacts": [
                    _artifact_summary(prompt_artifact),
                    _artifact_summary(raw_artifact),
                ],
            },
        )


def analyze_task_vision(
    session: Session,
    *,
    task: ImageTask,
    preview_artifact: ArtifactRef,
    metadata_artifact: ArtifactRef,
    settings: Settings | None = None,
    backend: VisionModelBackend | None = None,
    storage: ArtifactStorage | None = None,
) -> VisionAnalysisArtifacts:
    analyzer = VisionAnalyzer(settings=settings, backend=backend, storage=storage)
    return analyzer.analyze(
        session,
        task=task,
        preview_artifact=preview_artifact,
        metadata_artifact=metadata_artifact,
    )


def build_vision_prompt(*, metadata: dict[str, Any]) -> str:
    basic = metadata.get("basic", {})
    image = metadata.get("image", {})
    recipe_guidance = build_recipe_model_guidance()
    return (
        "Analyze the provided 1024px sRGB JPEG preview and EXIF/basic metadata for Tonevyra AI.\n"
        "Return JSON only with: scene_type, main_subject, usable, issues, correction_intents, confidence, risk_flags.\n"
        "The correction_intents object must contain numeric correction suggestions for the planner to validate.\n"
        "Use non-zero correction_intents when issues are detected; do not leave all values at zero for a correctable image.\n"
        "Do not output natural-language correction prose, final_develop_settings, lightroom_adjustments, or plugin commands.\n"
        f"{recipe_guidance}\n"
        f"Image metadata: {image}\n"
        f"Basic EXIF metadata: {basic}\n"
    )


def _artifact_summary(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
