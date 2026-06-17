from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskArtifactRepository
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.storage.artifacts import ArtifactStorage
from tonevyra_agent.vision.analyzer import VisionAnalyzer
from tonevyra_agent.vision.model import MockVisionBackend, QwenVisionBackend, create_vision_backend


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "qwen_t017"
MODEL_DIR = RUNTIME_DIR / "models"
QWEN_MODEL_DIR = MODEL_DIR / "qwen2.5-vl-3b-instruct-4bit"
VISION_FIXTURE = PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json"


VALID_QWEN_PAYLOAD = {
    "schema_version": "1.0",
    "scene_type": "underwater",
    "main_subject": "diver and reef",
    "usable": True,
    "issues": {
        "exposure": "slightly_underexposed",
        "color_cast": "blue_green",
        "haze": "moderate",
        "contrast": "low",
        "sharpness": "acceptable",
        "noise": "low",
    },
    "edit_intent": "restore underwater color balance while preserving a natural look",
    "confidence": 0.82,
    "risk_flags": [],
}


class FakeQwenRuntime:
    def __init__(self, output: str | dict[str, Any]) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def generate(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> str | dict[str, Any]:
        self.calls.append({"preview_path": preview_path, "metadata": metadata, "prompt": prompt})
        return self.output


def _settings() -> Settings:
    return Settings(
        runtime_dir=RUNTIME_DIR,
        input_dir=RUNTIME_DIR / "input",
        output_dir=RUNTIME_DIR / "output",
        artifact_dir=RUNTIME_DIR / "artifacts",
        preview_dir=RUNTIME_DIR / "previews",
        bridge_dir=RUNTIME_DIR / "bridge",
        log_dir=RUNTIME_DIR / "logs",
        models_dir=MODEL_DIR,
        vision_backend="qwen",
        qwen_model_path=QWEN_MODEL_DIR,
        qwen_model_name="Qwen2.5-VL-3B-Instruct-4bit",
        model_offline=True,
        vision_review_confidence_threshold=0.7,
        preview_long_edge=1024,
    )


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)
    QWEN_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (QWEN_MODEL_DIR / "LOCAL_MODEL_PLACEHOLDER.txt").write_text(
        "Harness placeholder only. Real model files are installed separately.",
        encoding="utf-8",
    )


def _cleanup_db(settings: Settings) -> None:
    task_repo = ImageTaskRepository()
    with session_scope(settings) as session:
        for name in ("qwen_valid.jpg", "qwen_invalid.jpg"):
            for task in task_repo.list_by_file_name(session, name):
                task_repo.delete(session, task)


def _prepare_source(settings: Settings, name: str) -> Path:
    source_path = settings.project_path(settings.input_dir) / name
    shutil.copy2(FIXTURE_IMAGE, source_path)
    return source_path


def _create_task_with_metadata_preview(settings: Settings, source_path: Path):
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path=source_path,
            file_name=source_path.name,
            file_ext=source_path.suffix.lower(),
            file_size_bytes=source_path.stat().st_size,
            status=TaskStatus.QUEUED,
            current_stage=Stage.WATCH,
        )
        metadata_preview = create_metadata_and_preview_artifacts(
            session,
            task=task,
            settings=settings,
            storage=storage,
        )
        return task.id, metadata_preview.metadata_artifact, metadata_preview.preview_artifact.artifact


def _run_analyzer(settings: Settings, *, task_id, metadata_ref, preview_ref, backend: QwenVisionBackend):
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    analyzer = VisionAnalyzer(settings=settings, backend=backend, storage=storage)
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task disappeared before Qwen analysis: {task_id}")
        return analyzer.analyze(
            session,
            task=task,
            preview_artifact=preview_ref,
            metadata_artifact=metadata_ref,
        )


def _run_analyzer_expect_error(settings: Settings, *, task_id, metadata_ref, preview_ref, backend: QwenVisionBackend) -> TonevyraError:
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    analyzer = VisionAnalyzer(settings=settings, backend=backend, storage=storage)
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task disappeared before Qwen analysis: {task_id}")
        try:
            analyzer.analyze(
                session,
                task=task,
                preview_artifact=preview_ref,
                metadata_artifact=metadata_ref,
            )
        except TonevyraError as exc:
            return exc
    raise RuntimeError("expected Qwen analyzer to raise TonevyraError")


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    _cleanup_db(settings)
    _reset_runtime(settings)

    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    storage = ArtifactStorage(settings=settings)

    mock_backend = create_vision_backend(Settings(vision_backend="mock", vision_mock_fixture=VISION_FIXTURE))
    if not isinstance(mock_backend, MockVisionBackend):
        return _fail("mock backend is no longer available")
    print("OK mock backend remains available")

    missing_settings = Settings(vision_backend="qwen", models_dir=MODEL_DIR, qwen_model_path=MODEL_DIR / "missing")
    try:
        create_vision_backend(missing_settings)
    except TonevyraError as exc:
        if exc.code != ErrorCode.MODEL_LOAD_FAILED:
            return _fail(f"missing local model path should fail with MODEL_LOAD_FAILED, got {exc.code.value}")
    else:
        return _fail("missing local model path should not load")
    print("OK missing local Qwen model path fails safely")

    outside_settings = Settings(vision_backend="qwen", models_dir=MODEL_DIR, qwen_model_path=PROJECT_ROOT / "README.md")
    try:
        create_vision_backend(outside_settings)
    except TonevyraError as exc:
        if exc.code != ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED:
            return _fail(f"outside model path should fail with SECURITY_NETWORK_ACCESS_BLOCKED, got {exc.code.value}")
    else:
        return _fail("outside model path should be blocked")
    print("OK Qwen model path must stay inside configured models_dir")

    valid_runtime = FakeQwenRuntime(json.dumps(VALID_QWEN_PAYLOAD))
    valid_backend = QwenVisionBackend(settings, runtime=valid_runtime)
    valid_id, valid_metadata, valid_preview = _create_task_with_metadata_preview(
        settings,
        _prepare_source(settings, "qwen_valid.jpg"),
    )
    valid = _run_analyzer(
        settings,
        task_id=valid_id,
        metadata_ref=valid_metadata,
        preview_ref=valid_preview,
        backend=valid_backend,
    )
    if valid.result.model_backend != "qwen":
        return _fail(f"expected qwen model_backend, got {valid.result.model_backend}")
    if not storage.exists(valid.structured_artifact) or not storage.verify_checksum(valid.structured_artifact):
        return _fail("Qwen structured artifact is missing or checksum-invalid")
    if not valid_runtime.calls:
        return _fail("fake Qwen runtime was not called")
    visible_metadata = valid_runtime.calls[0]["metadata"]
    if set(visible_metadata.keys()) - {"basic", "image"}:
        return _fail(f"Qwen runtime received metadata outside the allowed boundary: {visible_metadata.keys()}")
    print("OK local Qwen backend returned valid structured output through analyzer")

    invalid_backend = QwenVisionBackend(settings, runtime=FakeQwenRuntime({"model_backend": "qwen", "model_name": "bad-output"}))
    invalid_id, invalid_metadata, invalid_preview = _create_task_with_metadata_preview(
        settings,
        _prepare_source(settings, "qwen_invalid.jpg"),
    )
    exc = _run_analyzer_expect_error(
        settings,
        task_id=invalid_id,
        metadata_ref=invalid_metadata,
        preview_ref=invalid_preview,
        backend=invalid_backend,
    )
    if exc.code != ErrorCode.MODEL_OUTPUT_INVALID:
        return _fail(f"expected MODEL_OUTPUT_INVALID, got {exc.code.value}")
    print("OK invalid Qwen output is caught by schema validation")

    with session_scope(settings) as session:
        valid_task = task_repo.get(session, valid_id)
        invalid_task = task_repo.get(session, invalid_id)
        if valid_task is None or invalid_task is None:
            return _fail("Qwen test tasks are missing")
        if valid_task.status != TaskStatus.ANALYSIS_DONE.value:
            return _fail(f"valid Qwen task should be ANALYSIS_DONE, got {valid_task.status}")
        if invalid_task.status != TaskStatus.FAILED.value:
            return _fail(f"invalid Qwen task should be FAILED, got {invalid_task.status}")
        if invalid_task.error_code != ErrorCode.MODEL_OUTPUT_INVALID.value:
            return _fail(f"invalid Qwen task error_code should be MODEL_OUTPUT_INVALID, got {invalid_task.error_code}")

        valid_artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, valid_id)}
        required = {
            ArtifactType.VISION_PROMPT.value,
            ArtifactType.VISION_RAW_RESPONSE.value,
            ArtifactType.VISION_STRUCTURED.value,
        }
        if not required.issubset(valid_artifact_types):
            return _fail(f"valid Qwen task missing vision artifacts: {sorted(valid_artifact_types)}")
        invalid_artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, invalid_id)}
        if ArtifactType.VISION_RAW_RESPONSE.value not in invalid_artifact_types:
            return _fail("invalid Qwen task should persist raw response")
        if ArtifactType.VISION_STRUCTURED.value in invalid_artifact_types:
            return _fail("invalid Qwen task should not persist structured output")

        valid_stage_status = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, valid_id)}
        invalid_stage_status = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, invalid_id)}
        if (Stage.VISION.value, StageStatus.SUCCEEDED.value) not in valid_stage_status:
            return _fail("valid Qwen task missing successful vision stage_result")
        if (Stage.VISION.value, StageStatus.FAILED.value) not in invalid_stage_status:
            return _fail("invalid Qwen task missing failed vision stage_result")

        task_repo.delete(session, valid_task)
        task_repo.delete(session, invalid_task)
    print("OK Qwen DB state and artifacts verified")

    with session_scope(settings) as session:
        for task_id in (valid_id, invalid_id):
            if artifact_repo.list_for_task(session, task_id):
                return _fail(f"task_artifacts rows were not cleaned up for {task_id}")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("Local Qwen backend verification complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
