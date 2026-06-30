from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from tonevyra_agent.agent.runtime_snapshot import AgentRuntimeSnapshot
from tonevyra_agent.agent.runtime_state import AgentRuntimeState
from tonevyra_agent.cli import _tray_startup_command
from tonevyra_agent.windows.background_launcher import build_background_command
from tonevyra_agent.windows.shell_worker_ipc import TrayCommand, TrayCommandName, TrayCommandProcessor
from tonevyra_agent.windows.single_instance import SingleInstanceGuard
from tonevyra_agent.windows.tray_state import tray_presentation
from tonevyra_agent.windows.worker_supervisor import SupervisionPolicy, WorkerSupervisor


def test_single_instance_guard_rejects_second_owner() -> None:
    name = f"Local\\TonevyraAI.Test.{uuid4()}"
    first = SingleInstanceGuard(name)
    second = SingleInstanceGuard(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.release()
        first.release()


def test_tray_command_processor_is_idempotent() -> None:
    processor = TrayCommandProcessor()
    command = TrayCommand(command=TrayCommandName.PAUSE_WATCHING)

    first = processor.handle(command, current_state="WATCHING", apply=lambda _cmd: ("PAUSED", "paused"))
    second = processor.handle(command, current_state="WATCHING", apply=lambda _cmd: ("ERROR", "should not run"))

    assert first.status == "APPLIED"
    assert second.agent_state == "PAUSED"
    assert second.idempotent_replay is True


def test_worker_supervisor_stops_restart_crash_loop() -> None:
    supervisor = WorkerSupervisor(SupervisionPolicy(maximum_restarts_in_window=2, restart_backoff_seconds=(0.0,)))

    assert supervisor.restart_if_allowed(reason="crash").allowed is True
    assert supervisor.restart_if_allowed(reason="crash").allowed is True
    decision = supervisor.restart_if_allowed(reason="crash")

    assert decision.allowed is False
    assert decision.error_code == "WORKER_CRASH_LOOP"


def test_worker_supervisor_detects_heartbeat_timeout() -> None:
    old = (datetime.utcnow() - timedelta(seconds=30)).isoformat(timespec="seconds") + "Z"
    snapshot = AgentRuntimeSnapshot(
        agent_instance_id="agent-1",
        state=AgentRuntimeState.WATCHING,
        started_at=old,
        last_heartbeat_at=old,
        watching_enabled=True,
        watch_path="runtime/input",
        queue_depth=0,
        processing_count=0,
        failed_count=0,
        lightroom_connected=True,
        model_ready=True,
        db_ready=True,
        worker_restart_count=0,
    )
    supervisor = WorkerSupervisor(SupervisionPolicy(heartbeat_timeout_seconds=1))
    supervisor.observe_heartbeat(snapshot)

    assert supervisor.heartbeat_expired(datetime.utcnow()) is True


def test_tray_state_mapping_uses_warning_for_paused() -> None:
    presentation = tray_presentation(AgentRuntimeState.PAUSED)

    assert presentation.icon_name == "tonevyra_tray_warning.ico"


def test_tray_background_launcher_targets_background_command() -> None:
    command = build_background_command()

    assert command[-3:] == ["-m", "tonevyra_agent.cli", "background"]
    assert "tray" not in command


def test_tray_background_launcher_uses_frozen_executable_command() -> None:
    command = build_background_command(executable="TonevyraAI.exe", frozen=True)

    assert command == ["TonevyraAI.exe", "background"]


def test_tray_startup_command_uses_frozen_executable_directly() -> None:
    executable, args = _tray_startup_command("TonevyraAI.exe", frozen=True)

    assert executable == "TonevyraAI.exe"
    assert args == ["tray"]
