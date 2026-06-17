from __future__ import annotations

import shutil
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "metadata_preview_t004"


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
        preview_long_edge=1024,
    )


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)


def _cleanup_db(settings: Settings) -> None:
    task_repo = ImageTaskRepository()
    with session_scope(settings) as session:
        for task in task_repo.list_by_file_name(session, FIXTURE_IMAGE.name):
            task_repo.delete(session, task)


def _cleanup_artifact_files(refs: list[ArtifactRef]) -> None:
    task_dirs: set[Path] = set()
    for ref in refs:
        task_dirs.add(ref.absolute_path.parent)
        if ref.absolute_path.exists():
            ref.absolute_path.unlink()
    for task_dir in sorted(task_dirs, key=lambda item: len(item.parts), reverse=True):
        try:
            task_dir.rmdir()
        except OSError:
            pass


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    _cleanup_db(settings)
    _reset_runtime(settings)

    input_path = settings.project_path(settings.input_dir) / FIXTURE_IMAGE.name
    shutil.copy2(FIXTURE_IMAGE, input_path)

    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()
    storage = ArtifactStorage(settings=settings)

    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path=input_path,
            file_name=input_path.name,
            file_ext=input_path.suffix.lower(),
            file_size_bytes=input_path.stat().st_size,
            status=TaskStatus.QUEUED,
            current_stage=Stage.WATCH,
        )
        task_id = task.id
        result = create_metadata_and_preview_artifacts(
            session,
            task=task,
            settings=settings,
            storage=storage,
            stage_repository=stage_repo,
            event_repository=event_repo,
        )
        metadata_ref = result.metadata_artifact
        preview_ref = result.preview_artifact.artifact

    print(f"OK metadata and preview created for task {task_id}")

    metadata = storage.load_json(metadata_ref)
    if metadata["file"]["name"] != FIXTURE_IMAGE.name:
        return _fail("metadata artifact has unexpected file name")
    if metadata["image"]["readable"] is not True:
        return _fail("metadata artifact does not mark image as readable")
    print("OK EXIF/basic metadata artifact exists")

    if not storage.exists(preview_ref):
        return _fail("preview artifact file is missing")
    if not storage.verify_checksum(metadata_ref):
        return _fail("metadata checksum mismatch")
    if not storage.verify_checksum(preview_ref):
        return _fail("preview checksum mismatch")
    print("OK artifact checksums verified")

    with Image.open(preview_ref.absolute_path) as preview:
        if preview.format != "JPEG":
            return _fail(f"preview should be JPEG, got {preview.format}")
        if preview.mode != "RGB":
            return _fail(f"preview should be RGB, got {preview.mode}")
        if max(preview.size) > 1024:
            return _fail(f"preview long edge should be <= 1024, got {preview.size}")
        icc_profile = preview.info.get("icc_profile")
        if not icc_profile:
            return _fail("preview should include an sRGB ICC profile")
        profile_name = ImageCms.getProfileName(ImageCms.ImageCmsProfile(BytesIO(icc_profile)))
        if "sRGB" not in profile_name:
            return _fail(f"preview ICC profile should be sRGB, got {profile_name}")
    print("OK preview is sRGB-compatible RGB JPEG with long edge <= 1024")

    with session_scope(settings) as session:
        artifacts = artifact_repo.list_for_task(session, task_id)
        artifact_types = {artifact.artifact_type for artifact in artifacts}
        if artifact_types != {ArtifactType.EXIF_JSON.value, ArtifactType.PREVIEW_JPEG.value}:
            return _fail(f"unexpected artifact types: {sorted(artifact_types)}")

        stages = stage_repo.list_for_task(session, task_id)
        stage_status = {(stage.stage, stage.stage_status) for stage in stages}
        expected_stages = {
            (Stage.METADATA.value, StageStatus.SUCCEEDED.value),
            (Stage.PREVIEW.value, StageStatus.SUCCEEDED.value),
        }
        if stage_status != expected_stages:
            return _fail(f"unexpected stage_results: {sorted(stage_status)}")

        events = event_repo.list_for_task(session, task_id)
        if not any(event.event_type == TaskEventType.PREVIEW_CREATED.value for event in events):
            return _fail("PREVIEW_CREATED event was not recorded")

        task = task_repo.get(session, task_id)
        if task is None:
            return _fail("test task is missing before cleanup")
        if task.current_stage != Stage.PREVIEW.value:
            return _fail(f"task current_stage should be preview, got {task.current_stage}")
        task_repo.delete(session, task)
    print("OK stage_results and task_event recorded")

    with session_scope(settings) as session:
        if artifact_repo.list_for_task(session, task_id):
            return _fail("task_artifacts rows were not cleaned up")

    _cleanup_artifact_files([metadata_ref, preview_ref])
    print("OK metadata/preview test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
