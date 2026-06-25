"""CLI entry point for Tonevyra AI Agent."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from sqlalchemy.exc import SQLAlchemyError

from tonevyra_agent.agent.recovery import RecoveryManager
from tonevyra_agent.agent.runner import AgentRunner
from tonevyra_agent.agent.watcher import FolderWatcher
from tonevyra_agent.core.config import REQUIRED_DB_TABLES, REQUIRED_DB_VIEWS, Settings, get_settings
from tonevyra_agent.core.enums import FeedbackUserAction, TaskStatus
from tonevyra_agent.db.database import check_required_objects, create_db_engine, get_database_identity, session_scope
from tonevyra_agent.db.repositories import (
    FeedbackRecordRepository,
    ImageTaskRepository,
    LearningSampleRepository,
    QualityResultRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
    run_db_smoke_test,
)
from tonevyra_agent.learning.feedback import FeedbackCaptureService
from tonevyra_agent.learning.reference_pair import analyze_expert_reference_pair
from tonevyra_agent.learning.schemas import DevelopSettingsSnapshot, FeedbackCaptureRequest
from tonevyra_agent.vision.benchmark import run_model_benchmark
from tonevyra_agent.vision.model import create_vision_backend

app = typer.Typer(no_args_is_help=True, help="Tonevyra AI local photo correction agent.")
feedback_app = typer.Typer(no_args_is_help=True, help="Capture explicit local feedback.")
app.add_typer(feedback_app, name="feedback")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _render_results(results: list[CheckResult]) -> None:
    for result in results:
        marker = "OK" if result.ok else "FAIL"
        typer.echo(f"[{marker}] {result.name}: {result.detail}")


def _runtime_dir_check(settings: Settings) -> CheckResult:
    missing = [path for path in settings.required_runtime_dirs() if not path.exists()]
    if missing:
        detail = "missing " + ", ".join(str(path) for path in missing)
        return CheckResult("runtime directories", False, detail)
    return CheckResult("runtime directories", True, str(settings.project_path(settings.runtime_dir)))


def _writable_dir_check(name: str, path: Path) -> CheckResult:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", delete=True, dir=path, encoding="utf-8") as handle:
            handle.write("tonevyra doctor write test")
        return CheckResult(name, True, str(path))
    except OSError as exc:
        return CheckResult(name, False, f"{exc.__class__.__name__}: {exc}")


def _vision_backend_check(settings: Settings) -> CheckResult:
    backend = settings.vision_backend.lower()
    if backend == "mock":
        fixture = settings.project_path(settings.vision_mock_fixture)
        return CheckResult(
            "vision backend",
            fixture.exists(),
            f"mock fixture={fixture}",
        )
    if backend in {"module", "module-analysis", "t021_module"}:
        return CheckResult(
            "vision backend",
            True,
            f"{settings.vision_backend} local deterministic provider",
        )
    if backend in {"qwen", "qwen2.5-vl", "qwen25vl"}:
        model_path = settings.project_path(settings.qwen_model_path)
        return CheckResult(
            "vision backend",
            model_path.exists(),
            f"{settings.vision_backend} local_model={model_path}",
        )
    if backend in {"qwen3vl", "qwen3-vl", "qwen3"}:
        model_path = settings.project_path(settings.qwen3_model_path)
        return CheckResult(
            "vision backend",
            model_path.exists(),
            f"{settings.vision_backend} local_model={model_path}",
        )
    return CheckResult("vision backend", False, f"unsupported backend={settings.vision_backend}")


@app.command()
def doctor() -> None:
    """Verify Python, runtime folders, and PostgreSQL database contract."""

    settings = get_settings()
    results: list[CheckResult] = []

    python_ok = sys.version_info[:2] == (3, 11)
    results.append(CheckResult("python version", python_ok, platform.python_version()))
    results.append(_runtime_dir_check(settings))
    results.append(CheckResult("database url configured", bool(settings.database_url), "set" if settings.database_url else "missing"))
    results.append(_writable_dir_check("artifact root writable", settings.project_path(settings.artifact_dir)))
    results.append(_writable_dir_check("bridge requests writable", settings.project_path(settings.bridge_dir) / "requests"))
    results.append(
        CheckResult(
            "model offline mode",
            settings.model_offline,
            f"TONEVYRA_MODEL_OFFLINE={settings.model_offline}",
        )
    )
    results.append(
        CheckResult(
            "worker concurrency",
            settings.worker_concurrency == 1,
            str(settings.worker_concurrency),
        )
    )
    results.append(_vision_backend_check(settings))
    results.append(
        CheckResult(
            "lightroom backend",
            settings.lightroom_backend in {"fake", "lightroom"},
            settings.lightroom_backend,
        )
    )

    try:
        engine = create_db_engine(settings)
        identity = get_database_identity(engine)
        objects = check_required_objects(engine, settings)
        results.append(
            CheckResult(
                "postgresql connection",
                True,
                f"connected to {identity.database_name} as {identity.user_name}",
            )
        )
        results.append(
            CheckResult(
                "current_database",
                identity.database_name == "tonevyra_agent",
                identity.database_name,
            )
        )
        results.append(CheckResult("current_user", identity.user_name == "tonevyra_app", identity.user_name))
        results.append(
            CheckResult(
                "required tables",
                not objects.missing_tables,
                "all present" if not objects.missing_tables else ", ".join(objects.missing_tables),
            )
        )
        results.append(
            CheckResult(
                "required views",
                not objects.missing_views,
                "all present" if not objects.missing_views else ", ".join(objects.missing_views),
            )
        )
    except SQLAlchemyError as exc:
        results.append(CheckResult("postgresql connection", False, exc.__class__.__name__))

    _render_results(results)
    raise typer.Exit(0 if all(result.ok for result in results) else 1)


@app.command("db-smoke-test")
def db_smoke_test() -> None:
    """Insert, read, and delete one image task with one event."""

    try:
        with session_scope(get_settings()) as session:
            result = run_db_smoke_test(session)
    except SQLAlchemyError as exc:
        typer.echo(f"[FAIL] db smoke test: {exc.__class__.__name__}", err=True)
        raise typer.Exit(1) from exc

    if not result.read_back_ok or not result.deleted:
        typer.echo("[FAIL] db smoke test: CRUD verification failed", err=True)
        raise typer.Exit(1)

    typer.echo("[OK] db smoke test: created image_task, created task_event, read back, deleted task")
    typer.echo(f"task_id={result.task_id}")
    typer.echo(f"event_id={result.event_id}")


@app.command()
def init() -> None:
    """Create required local runtime directories."""

    settings = get_settings()
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)
    typer.echo("Initialized Tonevyra AI runtime folders.")


@app.command()
def start(scan: bool = typer.Option(True, "--scan/--no-scan", help="Scan input before processing one queued task.")) -> None:
    """Run startup recovery and one MVP processing cycle."""

    settings = get_settings()
    recovery = RecoveryManager(settings=settings).recover_all()
    with _fake_lightroom_worker(settings):
        result = AgentRunner(settings=settings).run_once(scan_input=scan)

    typer.echo(
        "Recovery inspected="
        f"{recovery.inspected_count} recovered={recovery.recovered_count} failed={recovery.failed_count}"
    )
    _render_run_once_result(result)


@app.command()
def stop() -> None:
    """Stop marker for the current CLI-first MVP."""

    settings = get_settings()
    lock_path = settings.project_path(settings.runtime_dir) / "tonevyra-agent.lock"
    if lock_path.exists():
        lock_path.unlink()
        typer.echo(f"Removed stale lock: {lock_path}")
        return
    typer.echo("No persistent Tonevyra AI process is managed by the current MVP CLI.")


@app.command()
def status(json_output: bool = typer.Option(False, "--json", help="Render machine-readable JSON.")) -> None:
    """Show task counts and the latest tasks."""

    task_repo = ImageTaskRepository()
    with session_scope(get_settings()) as session:
        counts = task_repo.count_by_status(session)
        recent = [_task_summary(task) for task in task_repo.list_recent(session, limit=10)]

    payload = {"counts": counts, "recent_tasks": recent}
    if json_output:
        typer.echo(_json_dump(payload))
        return

    for status_value in (status.value for status in TaskStatus):
        typer.echo(f"{status_value}: {counts.get(status_value, 0)}")
    if recent:
        typer.echo("Recent tasks:")
        for item in recent:
            typer.echo(f"- {item['id']} {item['status']} {item['file_name']}")


@app.command()
def tasks(
    status_filter: str | None = typer.Option(None, "--status", help="Filter by controlled task status."),
    limit: int = typer.Option(20, "--limit", min=1, max=200),
    json_output: bool = typer.Option(False, "--json", help="Render machine-readable JSON."),
) -> None:
    """List recent tasks, optionally filtered by status."""

    status_value = _parse_task_status(status_filter) if status_filter else None
    task_repo = ImageTaskRepository()
    with session_scope(get_settings()) as session:
        rows = [_task_summary(task) for task in task_repo.list_recent(session, limit=limit, status=status_value)]

    if json_output:
        typer.echo(_json_dump(rows))
        return
    if not rows:
        typer.echo("No tasks found.")
        return
    for item in rows:
        typer.echo(f"{item['id']} {item['status']} {item['current_stage']} {item['file_name']}")


@app.command()
def task(task_id: UUID, json_output: bool = typer.Option(False, "--json", help="Render machine-readable JSON.")) -> None:
    """Show one task with artifacts, stage results, quality, feedback, and events."""

    payload = _task_detail(task_id)
    if payload is None:
        typer.echo(f"Task not found: {task_id}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(_json_dump(payload))
        return
    item = payload["task"]
    typer.echo(f"Task: {item['id']}")
    typer.echo(f"Status: {item['status']} stage={item['current_stage']} retry_count={item['retry_count']}")
    typer.echo(f"File: {item['source_path']}")
    if item["error_code"]:
        typer.echo(f"Error: {item['error_code']} {item['error_message']}")
    typer.echo(f"Artifacts: {len(payload['artifacts'])}")
    typer.echo(f"Events: {len(payload['events'])}")


@app.command()
def scan(json_output: bool = typer.Option(False, "--json", help="Render machine-readable JSON.")) -> None:
    """Manually scan the configured input folder once."""

    settings = get_settings()
    with session_scope(settings) as session:
        result = FolderWatcher(settings).scan_once(session)
    payload = {
        "created_task_ids": result.created_task_ids,
        "skipped_task_ids": result.skipped_task_ids,
        "ignored_count": len(result.ignored_paths),
        "duplicate_count": len(result.duplicate_paths),
        "unstable_count": len(result.unstable_paths),
    }
    if json_output:
        typer.echo(_json_dump(payload))
        return
    typer.echo(
        f"created={len(result.created_task_ids)} skipped={len(result.skipped_task_ids)} "
        f"ignored={len(result.ignored_paths)} duplicates={len(result.duplicate_paths)} unstable={len(result.unstable_paths)}"
    )


@app.command()
def retry(
    task_id: UUID,
    process_now: bool = typer.Option(False, "--process-now", help="Process immediately after requeueing."),
) -> None:
    """Explicitly requeue a terminal non-PASS task for retry."""

    settings = get_settings()
    try:
        with _fake_lightroom_worker(settings) if process_now else _null_context():
            result = AgentRunner(settings=settings).retry_task(task_id, process_now=process_now)
    except ValueError as exc:
        typer.echo(f"[FAIL] retry: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result is None:
        typer.echo(f"[OK] task requeued for retry: {task_id}")
        return
    _render_worker_result(result)


@app.command()
def process(file_path: Path) -> None:
    """Process one explicit file through the normal mock/fake pipeline."""

    settings = get_settings()
    try:
        with _fake_lightroom_worker(settings):
            result = AgentRunner(settings=settings).process_file(file_path)
    except ValueError as exc:
        typer.echo(f"[FAIL] process: {exc}", err=True)
        raise typer.Exit(1) from exc
    _render_worker_result(result)


@app.command("test-lightroom")
def test_lightroom() -> None:
    """Run the Lightroom bridge validation harnesses."""

    _run_harness_script("run_fake_lightroom_test.py")
    _run_harness_script("verify_lightroom_plugin_poc.py")


@app.command("test-vision")
def test_vision() -> None:
    """Run the vision backend validation harnesses."""

    create_vision_backend(get_settings())
    _run_harness_script("run_vision_mock_test.py")
    _run_harness_script("run_qwen_backend_test.py")


@app.command("loop-events")
def loop_events(
    task_id: UUID,
    json_output: bool = typer.Option(False, "--json", help="Render machine-readable JSON."),
) -> None:
    """Show loop-related task events for one task."""

    event_repo = TaskEventRepository()
    with session_scope(get_settings()) as session:
        rows = [
            _event_summary(event)
            for event in event_repo.list_for_task(session, task_id)
            if (event.payload_json or {}).get("loop_name")
        ]
    if json_output:
        typer.echo(_json_dump(rows))
        return
    if not rows:
        typer.echo("No loop events found.")
        return
    for event in rows:
        payload = event["payload_json"]
        typer.echo(
            f"{event['created_at']} {payload.get('loop_name')} {event['event_type']} "
            f"{payload.get('from_status')}->{payload.get('to_status')} {payload.get('reason')}"
        )


@feedback_app.command("sync")
def feedback_sync(task_id: UUID) -> None:
    """Report feedback sync status for a task."""

    payload = _task_detail(task_id)
    if payload is None:
        typer.echo(f"Task not found: {task_id}", err=True)
        raise typer.Exit(1)
    typer.echo("Lightroom develop-settings sync is deferred until the real Lightroom bridge ticket.")
    typer.echo("Use feedback approve/reject to store explicit local feedback now.")


@feedback_app.command("approve")
def feedback_approve(
    task_id: UUID,
    use_for_learning: bool = typer.Option(True, "--use-for-learning/--no-use-for-learning"),
    rating: int = typer.Option(5, "--rating", min=1, max=5),
) -> None:
    """Store explicit approval feedback for a finished task."""

    _capture_feedback(
        task_id,
        FeedbackCaptureRequest(
            user_action=FeedbackUserAction.ACCEPTED,
            rating=rating,
            accepted=True,
            approved_for_learning=use_for_learning,
            ai_settings=DevelopSettingsSnapshot(source="cli_explicit_feedback"),
            final_settings=DevelopSettingsSnapshot(source="cli_explicit_feedback"),
        ),
    )


@feedback_app.command("reject")
def feedback_reject(
    task_id: UUID,
    reason: str = typer.Option(..., "--reason", help="Local reason tag, e.g. too_blue."),
    rating: int = typer.Option(1, "--rating", min=1, max=5),
) -> None:
    """Store explicit rejection feedback for a finished task."""

    _capture_feedback(
        task_id,
        FeedbackCaptureRequest(
            user_action=FeedbackUserAction.REJECTED,
            rating=rating,
            reason_tags=[reason],
            accepted=False,
            approved_for_learning=False,
            ai_settings=DevelopSettingsSnapshot(source="cli_explicit_feedback"),
            final_settings=DevelopSettingsSnapshot(source="cli_explicit_feedback"),
        ),
    )


@feedback_app.command("expert-pair")
def feedback_expert_pair(
    task_id: UUID,
    original_path: Path = typer.Option(..., "--original", help="Original/before image path."),
    corrected_path: Path = typer.Option(..., "--corrected", help="Expert-corrected/after image path."),
    use_for_learning: bool = typer.Option(True, "--use-for-learning/--no-use-for-learning"),
) -> None:
    """Analyze an expert before/after pair and store local calibration evidence."""

    task_repo = ImageTaskRepository()
    settings = get_settings()
    try:
        analysis = analyze_expert_reference_pair(original_path, corrected_path)
    except ValueError as exc:
        typer.echo(f"[FAIL] expert pair: {exc}", err=True)
        raise typer.Exit(1) from exc

    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            typer.echo(f"Task not found: {task_id}", err=True)
            raise typer.Exit(1)
        if task.status not in {
            TaskStatus.PASS.value,
            TaskStatus.REVIEW_REQUIRED.value,
            TaskStatus.FAILED.value,
            TaskStatus.SKIPPED.value,
        }:
            typer.echo(f"Expert-pair feedback requires a terminal task status, got {task.status}", err=True)
            raise typer.Exit(1)

        zero_adjustments = {key: 0.0 for key in analysis.suggested_lightroom_delta}
        flattened_metric_delta = {f"metric_delta_{key}": value for key, value in analysis.metric_delta.items()}
        request = FeedbackCaptureRequest(
            user_action=FeedbackUserAction.MANUAL_EDITED,
            rating=5,
            reason_tags=["expert_reference_pair", "planner_calibration"],
            accepted=False,
            approved_for_learning=use_for_learning,
            comment=analysis.reason_summary,
            ai_settings=DevelopSettingsSnapshot(
                source="expert_pair_original",
                settings={
                    "reference_path": analysis.original_path,
                    "confidence": analysis.confidence,
                    **zero_adjustments,
                },
            ),
            final_settings=DevelopSettingsSnapshot(
                source="expert_pair_corrected",
                settings={
                    "reference_path": analysis.corrected_path,
                    "confidence": analysis.confidence,
                    **flattened_metric_delta,
                    **analysis.suggested_lightroom_delta,
                },
            ),
        )
        persisted = FeedbackCaptureService(settings=settings).capture_feedback(session, task=task, request=request)
        storage = persisted.manual_edit_delta_artifact

    typer.echo(f"[OK] expert pair analyzed: confidence={analysis.confidence}")
    typer.echo(f"suggested_lightroom_delta={_json_dump(analysis.suggested_lightroom_delta)}")
    typer.echo(f"manual_edit_delta_artifact={storage.relative_path}")
    if persisted.result.learning_sample_id:
        typer.echo(f"learning_sample_id={persisted.result.learning_sample_id}")


@app.command("benchmark-models")
def benchmark_models(
    sample_set: str = typer.Option("harness", "--sample-set"),
    include_100_photo: bool = typer.Option(False, "--include-100-photo/--skip-100-photo"),
) -> None:
    """Run the bounded local model benchmark loop."""

    result = run_model_benchmark(
        settings=get_settings(),
        sample_set=sample_set,
        include_100_photo=include_100_photo,
    )
    recommendation = result.payload["recommendation"]
    typer.echo(f"[OK] model benchmark artifact: {result.artifact.relative_path}")
    typer.echo(f"sha256={result.artifact.sha256}")
    typer.echo(f"recommendation={recommendation['decision']}")
    typer.echo(f"default_backend_after={result.payload['default_backend_after']}")


def get_app_settings() -> Settings:
    return get_settings()


def _capture_feedback(task_id: UUID, request: FeedbackCaptureRequest) -> None:
    task_repo = ImageTaskRepository()
    settings = get_settings()
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            typer.echo(f"Task not found: {task_id}", err=True)
            raise typer.Exit(1)
        if task.status not in {TaskStatus.PASS.value, TaskStatus.REVIEW_REQUIRED.value, TaskStatus.FAILED.value, TaskStatus.SKIPPED.value}:
            typer.echo(f"Feedback requires a terminal task status, got {task.status}", err=True)
            raise typer.Exit(1)
        result = FeedbackCaptureService(settings=settings).capture_feedback(session, task=task, request=request)
    typer.echo(f"[OK] feedback captured: {result.result.feedback_id}")
    if result.result.learning_sample_id:
        typer.echo(f"learning_sample_id={result.result.learning_sample_id}")


@contextmanager
def _fake_lightroom_worker(settings: Settings):
    if settings.lightroom_backend != "fake":
        yield
        return

    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "harness" / "fake_lightroom" / "fake_lightroom_worker.py"),
        "--bridge-dir",
        str(settings.project_path(settings.bridge_dir)),
        "--poll-interval",
        "0.1",
    ]
    env = os.environ.copy()
    env["TONEVYRA_BRIDGE_DIR"] = str(settings.project_path(settings.bridge_dir))
    process_handle = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2], env=env)
    try:
        yield
    finally:
        process_handle.terminate()
        try:
            process_handle.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process_handle.kill()


@contextmanager
def _null_context():
    yield


def _run_harness_script(script_name: str) -> None:
    script_path = Path(__file__).resolve().parents[2] / "harness" / "scripts" / script_name
    result = subprocess.run([sys.executable, str(script_path)], cwd=Path(__file__).resolve().parents[2], check=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _render_run_once_result(result) -> None:
    if result.scan_result is not None:
        typer.echo(
            f"Scan created={len(result.scan_result.created_task_ids)} "
            f"skipped={len(result.scan_result.skipped_task_ids)}"
        )
    if result.worker_result is None:
        typer.echo("No queued task was processed.")
        return
    _render_worker_result(result.worker_result)


def _render_worker_result(result) -> None:
    status = result.final_status.value if result.final_status else "UNKNOWN"
    typer.echo(f"[OK] task={result.task_id} status={status}")
    if result.error_code:
        typer.echo(f"error_code={result.error_code.value}")
    if result.error_message:
        typer.echo(f"error_message={result.error_message}")
    if result.final_export_path:
        typer.echo(f"final_export_path={result.final_export_path}")


def _parse_task_status(value: str | None) -> TaskStatus | None:
    if value is None:
        return None
    try:
        return TaskStatus(value)
    except ValueError as exc:
        allowed = ", ".join(status.value for status in TaskStatus)
        raise typer.BadParameter(f"invalid status {value}; allowed: {allowed}") from exc


def _task_detail(task_id: UUID) -> dict[str, Any] | None:
    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    event_repo = TaskEventRepository()
    stage_repo = StageResultRepository()
    quality_repo = QualityResultRepository()
    feedback_repo = FeedbackRecordRepository()
    learning_repo = LearningSampleRepository()
    with session_scope(get_settings()) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            return None
        return {
            "task": _task_summary(task),
            "artifacts": [_artifact_summary(row) for row in artifact_repo.list_for_task(session, task_id)],
            "stage_results": [_stage_summary(row) for row in stage_repo.list_for_task(session, task_id)],
            "quality_results": [_quality_summary(row) for row in quality_repo.list_for_task(session, task_id)],
            "feedback_records": [_feedback_summary(row) for row in feedback_repo.list_for_task(session, task_id)],
            "learning_samples": [_learning_summary(row) for row in learning_repo.list_for_task(session, task_id)],
            "events": [_event_summary(row) for row in event_repo.list_for_task(session, task_id)],
        }


def _task_summary(task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "file_name": task.file_name,
        "source_path": task.source_path,
        "status": task.status,
        "current_stage": task.current_stage,
        "retry_count": task.retry_count,
        "overall_score": float(task.overall_score) if task.overall_score is not None else None,
        "quality_decision": task.quality_decision,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "failed_stage": task.failed_stage,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "completed_at": task.completed_at,
    }


def _artifact_summary(artifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.artifact_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "mime_type": artifact.mime_type,
        "version": artifact.version,
        "created_at": artifact.created_at,
    }


def _stage_summary(stage) -> dict[str, Any]:
    return {
        "id": str(stage.id),
        "stage": stage.stage,
        "stage_status": stage.stage_status,
        "summary_json": stage.summary_json,
        "duration_ms": stage.duration_ms,
        "created_at": stage.created_at,
    }


def _quality_summary(quality) -> dict[str, Any]:
    return {
        "id": str(quality.id),
        "overall_score": float(quality.overall_score),
        "decision": quality.decision,
        "reason_summary": quality.reason_summary,
        "created_at": quality.created_at,
    }


def _feedback_summary(feedback) -> dict[str, Any]:
    return {
        "id": str(feedback.id),
        "user_action": feedback.user_action,
        "rating": feedback.rating,
        "reason_tags": feedback.reason_tags,
        "accepted": feedback.accepted,
        "created_at": feedback.created_at,
    }


def _learning_summary(sample) -> dict[str, Any]:
    return {
        "id": str(sample.id),
        "feedback_id": str(sample.feedback_id) if sample.feedback_id else None,
        "sample_type": sample.sample_type,
        "sample_status": sample.sample_status,
        "dataset_path": sample.dataset_path,
        "created_at": sample.created_at,
    }


def _event_summary(event) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "stage": event.stage,
        "message": event.message,
        "payload_json": event.payload_json,
        "created_at": event.created_at,
    }


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    app()
