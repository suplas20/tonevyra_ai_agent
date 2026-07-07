"""T-030 per-user background Agent runtime."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from tonevyra_agent.agent.runtime_snapshot import AgentRuntimeSnapshot, RuntimeSnapshotStore
from tonevyra_agent.agent.runtime_state import AgentRuntimeState, reduce_runtime_state
from tonevyra_agent.agent.watcher import FolderWatcher
from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository
from tonevyra_agent.inference.lifecycle import ProcessInferenceWorkerController
from tonevyra_agent.lightroom.process import lightroom_classic_status, record_lightroom_required_message
from tonevyra_agent.windows.shell_worker_ipc import TrayCommand, TrayCommandName, TrayCommandProcessor
from tonevyra_agent.windows.single_instance import SingleInstanceGuard, per_user_mutex_name
from tonevyra_agent.windows.worker_supervisor import SupervisionPolicy, WorkerSupervisor


@dataclass
class BackgroundRuntimeResult:
    snapshot: AgentRuntimeSnapshot
    iterations: int
    evidence_paths: list[Path] = field(default_factory=list)


class BackgroundAgentRuntime:
    """Thin owner of watcher intake and the existing one-photo processing loop."""

    def __init__(self, settings: Settings | None = None, *, agent_instance_id: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.agent_instance_id = agent_instance_id or f"agent-{uuid4()}"
        self.started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.snapshot_store = RuntimeSnapshotStore(self.settings)
        self.command_processor = TrayCommandProcessor()
        self.supervisor = WorkerSupervisor(
            SupervisionPolicy(
                heartbeat_timeout_seconds=self.settings.worker_heartbeat_timeout_seconds,
                restart_window_seconds=self.settings.worker_restart_window_seconds,
                maximum_restarts_in_window=self.settings.worker_restart_limit,
            )
        )
        self.watch_paused = self._pause_file().exists()
        self.shutdown_requested = False
        self.initialized = False
        self.worker_restart_count = 0
        self.watcher = FolderWatcher(self.settings)
        self.inference_worker = ProcessInferenceWorkerController(self.settings)

    def run(self, *, max_iterations: int | None = None, poll_interval_seconds: float = 2.0) -> BackgroundRuntimeResult:
        with SingleInstanceGuard(per_user_mutex_name("Agent"), self.settings) as guard:
            if not guard.acquired:
                snapshot = self._snapshot(
                    state=AgentRuntimeState.ERROR,
                    degraded_reasons=["AGENT_INSTANCE_ALREADY_RUNNING"],
                    db_ready=True,
                    model_ready=True,
                    lightroom_connected=True,
                )
                path = self.snapshot_store.write(snapshot)
                return BackgroundRuntimeResult(snapshot=snapshot, iterations=0, evidence_paths=[path])

            self.initialized = True
            iterations = 0
            evidence_paths: list[Path] = []
            initial = self._snapshot()
            self.supervisor.observe_heartbeat(initial)
            evidence_paths.append(self.snapshot_store.write(initial))
            while not self.shutdown_requested:
                self._poll_commands()
                processing_count = 0
                degraded_reasons = None
                if not self.watch_paused and self.settings.watch_enabled:
                    self._scan_input()
                    lightroom_status = lightroom_classic_status(self.settings)
                    if lightroom_status.required and not lightroom_status.running:
                        degraded_reasons = [lightroom_status.reason or "LIGHTROOM_CLASSIC_NOT_RUNNING"]
                        record_lightroom_required_message(
                            self.settings,
                            status=lightroom_status,
                            notify=self.settings.lightroom_missing_notification_enabled,
                        )
                    elif self._queued_count() > 0:
                        self.inference_worker.ensure_started()
                worker_snapshot = self.inference_worker.tick()
                processing_count = 1 if worker_snapshot.pid is not None else 0
                snapshot = self._snapshot(
                    processing_count=processing_count,
                    degraded_reasons=degraded_reasons,
                    lightroom_connected=not bool(degraded_reasons),
                    model_ready=not bool(degraded_reasons),
                )
                self.supervisor.observe_heartbeat(snapshot)
                evidence_paths.append(self.snapshot_store.write(snapshot))
                iterations += 1
                if max_iterations is not None and iterations >= max_iterations:
                    break
                time.sleep(poll_interval_seconds)

            stopped = self._snapshot(state=AgentRuntimeState.STOPPED, watching_enabled=False)
            self.inference_worker.force_stop(timeout_seconds=self.settings.graceful_shutdown_timeout_seconds)
            evidence_paths.append(self.snapshot_store.write(stopped))
            return BackgroundRuntimeResult(snapshot=stopped, iterations=iterations, evidence_paths=evidence_paths)

    def pause(self) -> None:
        self._pause_file().parent.mkdir(parents=True, exist_ok=True)
        self._pause_file().write_text("paused", encoding="utf-8")
        self.watch_paused = True
        self.snapshot_store.write(self._snapshot(state=AgentRuntimeState.PAUSED))

    def resume(self) -> None:
        self._pause_file().unlink(missing_ok=True)
        self.watch_paused = False
        self.snapshot_store.write(self._snapshot())

    def rescan(self) -> None:
        if not self.watch_paused:
            self._scan_input()
            if self._queued_count() > 0:
                self.inference_worker.ensure_started()
        self.snapshot_store.write(self._snapshot())

    def shutdown(self) -> None:
        self.shutdown_requested = True
        self.snapshot_store.write(self._snapshot(state=AgentRuntimeState.STOPPING))

    def handle_command(self, command: TrayCommand):
        return self.command_processor.handle(command, current_state=self._snapshot().state.value, apply=self._apply_command)

    def _apply_command(self, command: TrayCommand) -> tuple[str, str]:
        if command.command == TrayCommandName.GET_STATUS:
            return self._snapshot().state.value, "status returned"
        if command.command == TrayCommandName.PAUSE_WATCHING:
            self.pause()
            return AgentRuntimeState.PAUSED.value, "watching paused"
        if command.command == TrayCommandName.RESUME_WATCHING:
            self.resume()
            return self._snapshot().state.value, "watching resumed"
        if command.command == TrayCommandName.RESCAN:
            self.rescan()
            return self._snapshot().state.value, "rescan requested"
        if command.command == TrayCommandName.SHUTDOWN:
            self.shutdown()
            return AgentRuntimeState.STOPPING.value, "shutdown requested"
        return self._snapshot().state.value, "command accepted by shell boundary"

    def _poll_commands(self) -> None:
        command_path = self.settings.project_path(self.settings.runtime_dir) / "tray_command.json"
        if not command_path.exists():
            return
        try:
            command = TrayCommand.model_validate(json.loads(command_path.read_text(encoding="utf-8")))
            self.handle_command(command)
        finally:
            command_path.unlink(missing_ok=True)

    def _snapshot(
        self,
        *,
        state: AgentRuntimeState | None = None,
        watching_enabled: bool | None = None,
        processing_count: int = 0,
        degraded_reasons: list[str] | None = None,
        db_ready: bool = True,
        model_ready: bool = True,
        lightroom_connected: bool = True,
    ) -> AgentRuntimeSnapshot:
        counts = self._task_counts() if db_ready else {}
        failed_count = counts.get(TaskStatus.FAILED.value, 0) + counts.get(TaskStatus.REVIEW_REQUIRED.value, 0)
        queue_depth = counts.get(TaskStatus.QUEUED.value, 0)
        effective_state = state or reduce_runtime_state(
            initialized=self.initialized,
            shutdown_requested=self.shutdown_requested,
            watch_paused=self.watch_paused,
            degraded_reasons=degraded_reasons,
            processing_count=processing_count,
        )
        return AgentRuntimeSnapshot(
            agent_instance_id=self.agent_instance_id,
            state=effective_state,
            started_at=self.started_at,
            last_heartbeat_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            watching_enabled=(not self.watch_paused and self.settings.watch_enabled)
            if watching_enabled is None
            else watching_enabled,
            watch_path=str(self.settings.project_path(self.settings.input_dir).resolve()),
            recursive=self.settings.watch_recursive,
            queue_depth=queue_depth,
            processing_count=processing_count,
            failed_count=failed_count,
            active_job_id=None,
            lightroom_connected=lightroom_connected,
            model_ready=model_ready,
            db_ready=db_ready,
            degraded_reasons=degraded_reasons or [],
            worker_restart_count=self.worker_restart_count,
        )

    def _task_counts(self) -> dict[str, int]:
        try:
            with session_scope(self.settings) as session:
                return ImageTaskRepository().count_by_status(session)
        except Exception:  # noqa: BLE001 - snapshot degrades instead of crashing tray/runtime
            return {}

    def _queued_count(self) -> int:
        return self._task_counts().get(TaskStatus.QUEUED.value, 0)

    def _scan_input(self) -> None:
        with session_scope(self.settings) as session:
            self.watcher.scan_once(session)

    def _pause_file(self) -> Path:
        return self.settings.project_path(self.settings.runtime_dir) / "watch.paused"


def write_tray_command(command: TrayCommand, settings: Settings | None = None) -> Path:
    config = settings or get_settings()
    path = config.project_path(config.runtime_dir) / "tray_command.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(command.model_dump_json(indent=2), encoding="utf-8")
    return path
