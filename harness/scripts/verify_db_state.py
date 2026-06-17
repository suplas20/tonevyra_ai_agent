from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, QualityDecision, Stage, StageStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.models import VTaskSummary
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    QualityResultRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)


DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "smoke_t010"
DEFAULT_MANIFEST = DEFAULT_RUNTIME_DIR / "smoke_result.json"


def _settings(runtime_dir: Path) -> Settings:
    return Settings(
        runtime_dir=runtime_dir,
        input_dir=runtime_dir / "input",
        output_dir=runtime_dir / "output",
        artifact_dir=runtime_dir / "artifacts",
        preview_dir=runtime_dir / "previews",
        bridge_dir=runtime_dir / "bridge",
        log_dir=runtime_dir / "logs",
        models_dir=PROJECT_ROOT / "models",
        vision_backend="mock",
        lightroom_backend="fake",
    )


def _load_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"smoke manifest does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("runtime_dir", "task_id", "final_status", "final_export_path"):
        if not payload.get(key):
            raise RuntimeError(f"smoke manifest is missing {key}: {path}")
    return payload


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def verify_smoke_db_state(manifest_path: Path) -> int:
    manifest = _load_manifest(manifest_path)
    runtime_dir = Path(manifest["runtime_dir"]).resolve()
    settings = _settings(runtime_dir)
    task_id = UUID(manifest["task_id"])
    expected_status = manifest["final_status"]
    final_export_path = Path(manifest["final_export_path"])

    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()
    quality_repo = QualityResultRepository()

    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            return _fail(f"smoke task does not exist: {task_id}")
        if task.status not in {item.value for item in QualityDecision}:
            return _fail(f"task final status is not controlled: {task.status}")
        if task.status != expected_status:
            return _fail(f"task status {task.status} != manifest status {expected_status}")
        if task.current_stage != Stage.QUALITY.value:
            return _fail(f"task current_stage should be quality, got {task.current_stage}")
        if task.quality_decision != task.status:
            return _fail("task quality_decision should match final status")
        if task.overall_score is None:
            return _fail("task overall_score is missing")
        if task.completed_at is None:
            return _fail("task completed_at is missing")
        if not final_export_path.exists():
            return _fail(f"final export path from manifest does not exist: {final_export_path}")
        if "temp" in final_export_path.parts:
            return _fail(f"final export still points inside output/temp: {final_export_path}")

        artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, task_id)}
        required_artifacts = {
            ArtifactType.EXIF_JSON.value,
            ArtifactType.PREVIEW_JPEG.value,
            ArtifactType.VISION_PROMPT.value,
            ArtifactType.VISION_RAW_RESPONSE.value,
            ArtifactType.VISION_STRUCTURED.value,
            ArtifactType.CORRECTION_PLAN.value,
            ArtifactType.LIGHTROOM_REQUEST.value,
            ArtifactType.LIGHTROOM_RESPONSE.value,
            ArtifactType.EXPORTED_IMAGE.value,
            ArtifactType.QUALITY_DETAIL.value,
        }
        missing_artifacts = required_artifacts - artifact_types
        if missing_artifacts:
            return _fail(f"missing required artifact rows: {sorted(missing_artifacts)}")

        stage_statuses = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, task_id)}
        required_stages = {
            (Stage.METADATA.value, StageStatus.SUCCEEDED.value),
            (Stage.PREVIEW.value, StageStatus.SUCCEEDED.value),
            (Stage.VISION.value, StageStatus.SUCCEEDED.value),
            (Stage.CORRECTION_PLAN.value, StageStatus.SUCCEEDED.value),
            (Stage.LIGHTROOM.value, StageStatus.SUCCEEDED.value),
            (Stage.EXPORT.value, StageStatus.SUCCEEDED.value),
            (Stage.QUALITY.value, StageStatus.SUCCEEDED.value),
        }
        missing_stages = required_stages - stage_statuses
        if missing_stages:
            return _fail(f"missing required stage_results: {sorted(missing_stages)}")

        quality_rows = quality_repo.list_for_task(session, task_id)
        if len(quality_rows) != 1:
            return _fail(f"expected one quality_results row, got {len(quality_rows)}")
        if quality_rows[0].decision != task.status:
            return _fail("quality_results decision should match task status")

        events = event_repo.list_for_task(session, task_id)
        seen_loops = {event.payload_json.get("loop_name") for event in events}
        if "watch_loop" not in seen_loops:
            return _fail("missing watch_loop event evidence")
        if "processing_loop" not in seen_loops:
            return _fail("missing processing_loop event evidence")
        if "quality_loop" not in seen_loops:
            return _fail("missing quality_loop event evidence")

        summary = session.get(VTaskSummary, task_id)
        if summary is None:
            return _fail("v_task_summary row is missing")
        if summary.status != task.status:
            return _fail("v_task_summary status does not match image_tasks status")
        if not summary.artifact_count or summary.artifact_count < len(required_artifacts):
            return _fail(f"v_task_summary artifact_count is too low: {summary.artifact_count}")

    print(f"OK smoke DB state verified for task {task_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify DB state for the Tonevyra AI smoke pipeline.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    try:
        return verify_smoke_db_state(args.manifest.resolve())
    except Exception as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
