from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from tonevyra_agent.agent.runtime_snapshot import AgentRuntimeSnapshot
from tonevyra_agent.agent.runtime_state import AgentRuntimeState
from tonevyra_agent.cli import _tray_startup_command
from tonevyra_agent.core.config import Settings
from tonevyra_agent.windows import tray_shell
from tonevyra_agent.windows.app_entry import _notify_planner_startup_issue
from tonevyra_agent.windows.background_launcher import build_background_command
from tonevyra_agent.windows.shell_worker_ipc import TrayCommand, TrayCommandName, TrayCommandProcessor
from tonevyra_agent.windows.single_instance import SingleInstanceGuard
from tonevyra_agent.windows.tray_shell import TrayShell
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


def test_planner_startup_failure_is_shown_as_korean_user_error(monkeypatch) -> None:
    shown: dict[str, str] = {}

    def fail_readiness(_self):
        from tonevyra_agent.core.enums import ErrorCode, Stage
        from tonevyra_agent.core.errors import TonevyraError

        raise TonevyraError(
            code=ErrorCode.PLANNER_API_UNAVAILABLE,
            message="connection refused",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )

    monkeypatch.setattr("tonevyra_agent.core.config.get_settings", lambda: Settings(planner_api_mode="api"))
    monkeypatch.setattr("tonevyra_agent.planner_api.client.PlannerApiClient.check_readiness", fail_readiness)
    monkeypatch.setattr(
        "tonevyra_agent.windows.user_notifications.show_error_message",
        lambda title, message: shown.update(title=title, message=message) or True,
    )

    _notify_planner_startup_issue()

    assert "플래너 서버 오류" in shown["title"]
    assert "플래너 서버에 연결할 수 없습니다" in shown["message"]
    assert "PLANNER_API_UNAVAILABLE" in shown["message"]


def test_tray_shell_skips_worker_launch_when_background_is_already_running(monkeypatch, tmp_path: Path) -> None:
    calls = {"started": 0, "stopped": 0}

    class FakeGuard:
        acquired = True

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return None

    class FakeLauncher:
        def __init__(self, _settings):
            pass

        def is_background_running(self) -> bool:
            return True

        def start(self):
            calls["started"] += 1

        def stop(self) -> None:
            calls["stopped"] += 1

    class FakeTray:
        def __init__(self, _icon_path, *, tooltip: str):
            self.tooltip = tooltip

        def show_for(self, _seconds):
            return SimpleNamespace(added=True, removed=True, error_code=None)

    monkeypatch.setattr(tray_shell, "SingleInstanceGuard", lambda *_args, **_kwargs: FakeGuard())
    monkeypatch.setattr(tray_shell, "BackgroundWorkerLauncher", FakeLauncher)
    monkeypatch.setattr(tray_shell, "NativeTrayIcon", FakeTray)
    monkeypatch.setattr(
        tray_shell,
        "tray_icon_status",
        lambda: SimpleNamespace(
            production_ready=True,
            icons={"tonevyra_tray.ico": tmp_path / "tonevyra_tray.ico"},
            blocked_code=None,
        ),
    )

    result = TrayShell(settings=Settings(runtime_dir=tmp_path)).run(probe_seconds=0.01, start_background=True)

    assert result == 0
    assert calls == {"started": 0, "stopped": 0}


def test_tray_shell_starts_and_stops_worker_when_no_background_is_running(monkeypatch, tmp_path: Path) -> None:
    calls = {"started": 0, "stopped": 0}

    class FakeGuard:
        acquired = True

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return None

    class FakeLauncher:
        def __init__(self, _settings):
            pass

        def is_background_running(self) -> bool:
            return False

        def start(self):
            calls["started"] += 1

        def stop(self) -> None:
            calls["stopped"] += 1

    class FakeTray:
        def __init__(self, _icon_path, *, tooltip: str):
            self.tooltip = tooltip

        def show_for(self, _seconds):
            return SimpleNamespace(added=True, removed=True, error_code=None)

    monkeypatch.setattr(tray_shell, "SingleInstanceGuard", lambda *_args, **_kwargs: FakeGuard())
    monkeypatch.setattr(tray_shell, "BackgroundWorkerLauncher", FakeLauncher)
    monkeypatch.setattr(tray_shell, "NativeTrayIcon", FakeTray)
    monkeypatch.setattr(
        tray_shell,
        "tray_icon_status",
        lambda: SimpleNamespace(
            production_ready=True,
            icons={"tonevyra_tray.ico": tmp_path / "tonevyra_tray.ico"},
            blocked_code=None,
        ),
    )

    result = TrayShell(settings=Settings(runtime_dir=tmp_path)).run(probe_seconds=0.01, start_background=True)

    assert result == 0
    assert calls == {"started": 1, "stopped": 1}
