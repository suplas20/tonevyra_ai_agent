from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, Stage
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskArtifactRepository
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


DEFAULT_SMOKE_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "smoke_t010"
DEFAULT_SMOKE_MANIFEST = DEFAULT_SMOKE_RUNTIME_DIR / "smoke_result.json"


def _print_ok(message: str) -> None:
    print(f"OK {message}")


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def _cleanup_artifact_files(refs: list[ArtifactRef]) -> None:
    task_dirs: set[Path] = set()
    for ref in refs:
        path = ref.absolute_path
        task_dirs.add(path.parent)
        if path.exists():
            path.unlink()
    for task_dir in sorted(task_dirs, key=lambda item: len(item.parts), reverse=True):
        try:
            task_dir.rmdir()
        except OSError:
            pass


def _settings_for_runtime(runtime_dir: Path) -> Settings:
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


def _load_smoke_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"smoke manifest does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("runtime_dir", "task_id", "final_export_path"):
        if not payload.get(key):
            raise RuntimeError(f"smoke manifest is missing {key}: {path}")
    return payload


def _verify_smoke_artifacts(manifest_path: Path) -> int:
    manifest = _load_smoke_manifest(manifest_path)
    settings = _settings_for_runtime(Path(manifest["runtime_dir"]).resolve())
    task_id = UUID(manifest["task_id"])
    final_export_path = Path(manifest["final_export_path"])
    artifact_repo = TaskArtifactRepository()
    storage = ArtifactStorage(settings=settings)

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

    with session_scope(settings) as session:
        rows = artifact_repo.list_for_task(session, task_id)
        artifact_types = {row.artifact_type for row in rows}
        missing = required_artifacts - artifact_types
        if missing:
            return _fail(f"smoke task missing artifact rows: {sorted(missing)}")

        for row in rows:
            if row.artifact_type not in required_artifacts:
                continue
            if not storage.exists(row):
                return _fail(f"smoke artifact file missing: {row.artifact_path}")
            if not storage.verify_checksum(row):
                return _fail(f"smoke artifact checksum mismatch: {row.artifact_path}")
            _print_ok(f"smoke checksum verified {row.artifact_path}")

    if not final_export_path.exists():
        return _fail(f"final export file missing: {final_export_path}")
    if "temp" in final_export_path.parts:
        return _fail(f"final export should not remain in output/temp: {final_export_path}")
    _print_ok(f"final export exists outside temp: {final_export_path}")
    print("Smoke artifact verification complete.")
    return 0


def _run_artifact_storage_self_test() -> int:
    settings = get_settings()
    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    storage = ArtifactStorage(settings=settings)
    refs: list[ArtifactRef] = []

    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path="runtime/input/__tonevyra_artifact_storage_test__.jpg",
            file_name="__tonevyra_artifact_storage_test__.jpg",
            file_ext=".jpg",
            file_size_bytes=0,
            current_stage=Stage.WATCH,
        )
        task_id = task.id

        refs.append(
            storage.save_json(
                session,
                task_id=task_id,
                artifact_type=ArtifactType.EXIF_JSON,
                name="test_artifact.json",
                data={"ticket": "T-002", "kind": "json"},
            )
        )
        refs.append(
            storage.save_text(
                session,
                task_id=task_id,
                artifact_type=ArtifactType.VISION_PROMPT,
                name="test_artifact.txt",
                text="Tonevyra AI artifact storage test",
            )
        )
        refs.append(
            storage.save_bytes(
                session,
                task_id=task_id,
                artifact_type=ArtifactType.VISION_RAW_RESPONSE,
                name="test_artifact.bin",
                data=b"tonevyra-artifact-storage-test",
                mime_type="application/octet-stream",
            )
        )

        rows = artifact_repo.list_for_task(session, task_id)
        if len(rows) != 3:
            return _fail(f"expected 3 task_artifacts rows before commit, got {len(rows)}")

    _print_ok(f"created task {task_id}")

    json_ref, text_ref, bin_ref = refs
    if storage.load_json(json_ref) != {"kind": "json", "ticket": "T-002"}:
        return _fail("load_json returned unexpected content")
    _print_ok("load_json verified")

    if storage.load_text(text_ref) != "Tonevyra AI artifact storage test":
        return _fail("load_text returned unexpected content")
    _print_ok("load_text verified")

    for ref in refs:
        if not storage.exists(ref):
            return _fail(f"artifact file missing: {ref.relative_path}")
        if not storage.verify_checksum(ref):
            return _fail(f"checksum mismatch: {ref.relative_path}")
        _print_ok(f"checksum verified {ref.relative_path}")

    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            return _fail("test task was not persisted")
        rows = artifact_repo.list_for_task(session, task_id)
        if len(rows) != 3:
            return _fail(f"expected 3 persisted task_artifacts rows, got {len(rows)}")
        _print_ok("task_artifacts rows persisted")
        task_repo.delete(session, task)

    with session_scope(settings) as session:
        remaining = artifact_repo.list_for_task(session, task_id)
        if remaining:
            return _fail(f"expected task_artifacts cascade cleanup, got {len(remaining)} rows")
    _print_ok("database cleanup verified")

    _cleanup_artifact_files(refs)
    _print_ok("artifact file cleanup complete")
    print("Artifact storage verification complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Tonevyra AI artifact storage or smoke pipeline artifacts.")
    parser.add_argument("--smoke", action="store_true", help="Verify the default smoke pipeline artifact set.")
    parser.add_argument("--manifest", type=Path, default=None, help="Smoke manifest path.")
    parser.add_argument("--runtime-dir", type=Path, default=None, help="Smoke runtime dir containing smoke_result.json.")
    args = parser.parse_args()

    manifest_path = args.manifest
    if manifest_path is None and args.runtime_dir is not None:
        manifest_path = args.runtime_dir / "smoke_result.json"
    if args.smoke or manifest_path is not None:
        try:
            return _verify_smoke_artifacts((manifest_path or DEFAULT_SMOKE_MANIFEST).resolve())
        except Exception as exc:
            return _fail(str(exc))

    return _run_artifact_storage_self_test()


if __name__ == "__main__":
    raise SystemExit(main())
