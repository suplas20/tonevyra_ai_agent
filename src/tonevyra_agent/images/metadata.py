"""EXIF and basic image metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from PIL import ExifTags, Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskEventType
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import StageResultRepository, TaskEventRepository
from tonevyra_agent.images.preview import PreviewArtifactResult, create_preview_artifact
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


EXIF_FIELD_ALIASES: dict[str, str] = {
    "Make": "camera_make",
    "Model": "camera_model",
    "LensModel": "lens_model",
    "DateTimeOriginal": "captured_at",
    "ISOSpeedRatings": "iso",
    "ExposureTime": "exposure_time",
    "FNumber": "f_number",
    "FocalLength": "focal_length",
    "Orientation": "orientation",
    "ColorSpace": "color_space",
}


@dataclass(frozen=True)
class MetadataPreviewResult:
    metadata_artifact: ArtifactRef
    preview_artifact: PreviewArtifactResult


def extract_basic_metadata(source_path: Path) -> dict[str, Any]:
    """Return JSON-safe basic metadata and selected EXIF fields."""

    path = source_path.resolve()
    stat = path.stat()
    metadata: dict[str, Any] = {
        "source_path": str(path),
        "file": {
            "name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
        },
        "image": {
            "format": None,
            "width": None,
            "height": None,
            "mode": None,
            "readable": False,
        },
        "exif": {},
        "basic": {},
    }

    try:
        with Image.open(path) as image:
            metadata["image"] = {
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "readable": True,
            }
            exif = image.getexif()
    except (OSError, UnidentifiedImageError) as exc:
        raise TonevyraError(
            code=ErrorCode.PREVIEW_GENERATION_FAILED,
            message=f"Unable to read image metadata: {path}",
            failed_stage=Stage.METADATA.value,
        ) from exc

    named_exif = _named_exif(exif)
    metadata["exif"] = named_exif
    metadata["basic"] = {
        alias: named_exif.get(exif_name)
        for exif_name, alias in EXIF_FIELD_ALIASES.items()
        if named_exif.get(exif_name) is not None
    }
    metadata["has_exif"] = bool(named_exif)
    return metadata


def save_metadata_artifact(
    session: Session,
    *,
    task_id: UUID,
    source_path: Path,
    storage: ArtifactStorage | None = None,
) -> ArtifactRef:
    artifact_storage = storage or ArtifactStorage()
    metadata = extract_basic_metadata(source_path)
    return artifact_storage.save_json(
        session,
        task_id=task_id,
        artifact_type=ArtifactType.EXIF_JSON,
        name="exif.json",
        data=metadata,
    )


def create_metadata_and_preview_artifacts(
    session: Session,
    *,
    task: ImageTask,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
    stage_repository: StageResultRepository | None = None,
    event_repository: TaskEventRepository | None = None,
) -> MetadataPreviewResult:
    config = settings or get_settings()
    artifact_storage = storage or ArtifactStorage(config)
    stage_repo = stage_repository or StageResultRepository()
    event_repo = event_repository or TaskEventRepository()
    source_path = Path(task.source_path)

    metadata_started = datetime.utcnow()
    metadata_artifact = save_metadata_artifact(
        session,
        task_id=task.id,
        source_path=source_path,
        storage=artifact_storage,
    )
    metadata_finished = datetime.utcnow()
    stage_repo.create(
        session,
        task_id=task.id,
        stage=Stage.METADATA,
        stage_status=StageStatus.SUCCEEDED,
        started_at=metadata_started,
        finished_at=metadata_finished,
        duration_ms=_duration_ms(metadata_started, metadata_finished),
        summary_json=_artifact_summary(metadata_artifact),
    )

    preview_started = datetime.utcnow()
    preview_artifact = create_preview_artifact(
        session,
        task_id=task.id,
        source_path=source_path,
        settings=config,
        storage=artifact_storage,
    )
    preview_finished = datetime.utcnow()
    stage_repo.create(
        session,
        task_id=task.id,
        stage=Stage.PREVIEW,
        stage_status=StageStatus.SUCCEEDED,
        started_at=preview_started,
        finished_at=preview_finished,
        duration_ms=_duration_ms(preview_started, preview_finished),
        summary_json=preview_artifact.summary(),
    )

    task.current_stage = Stage.PREVIEW.value
    event_repo.create(
        session,
        task_id=task.id,
        event_type=TaskEventType.PREVIEW_CREATED,
        stage=Stage.PREVIEW,
        message="Metadata and 1024px preview artifacts created.",
        payload_json={
            "loop_name": "processing_loop",
            "loop_iteration": 1,
            "event_type": TaskEventType.PREVIEW_CREATED.value,
            "from_status": task.status,
            "to_status": task.status,
            "reason": "metadata and preview artifacts saved",
            "evidence_artifacts": [
                _artifact_summary(metadata_artifact),
                preview_artifact.summary(),
            ],
        },
    )
    session.flush()
    return MetadataPreviewResult(metadata_artifact=metadata_artifact, preview_artifact=preview_artifact)


def _named_exif(exif: Image.Exif) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for tag_id, value in exif.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        result[name] = _json_safe(value)
    return result


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if numerator is not None and denominator:
        return float(value)
    return str(value)
