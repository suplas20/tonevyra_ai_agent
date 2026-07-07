from __future__ import annotations

from contextlib import contextmanager

from tonevyra_agent.agent import runner as runner_module
from tonevyra_agent.agent.runner import AgentRunner
from tonevyra_agent.core.config import Settings
from tonevyra_agent.lightroom import process as lightroom_process
from tonevyra_agent.lightroom.process import (
    LIGHTROOM_CLASSIC_NOT_RUNNING,
    LightroomProcessStatus,
    lightroom_classic_status,
    record_lightroom_required_message,
)


def test_lightroom_status_blocks_real_backend_when_process_missing(tmp_path) -> None:
    settings = Settings(runtime_dir=tmp_path / "runtime", lightroom_backend="lightroom")

    status = lightroom_classic_status(settings, process_checker=lambda _name: False)

    assert status.required is True
    assert status.running is False
    assert status.reason == LIGHTROOM_CLASSIC_NOT_RUNNING


def test_lightroom_status_ignores_fake_backend(tmp_path) -> None:
    settings = Settings(runtime_dir=tmp_path / "runtime", lightroom_backend="fake")

    status = lightroom_classic_status(settings, process_checker=lambda _name: False)

    assert status.required is False
    assert status.running is True


def test_record_lightroom_message_is_rate_limited(tmp_path, monkeypatch) -> None:
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        lightroom_backend="lightroom",
        lightroom_missing_notification_cooldown_seconds=300,
    )
    status = LightroomProcessStatus(
        required=True,
        running=False,
        process_names=("Lightroom.exe",),
        reason=LIGHTROOM_CLASSIC_NOT_RUNNING,
        message="Start Lightroom Classic.",
    )
    launched: list[list[str]] = []
    monkeypatch.setattr(lightroom_process.os, "name", "nt")

    record_lightroom_required_message(settings, status=status, launcher=launched.append)
    record_lightroom_required_message(settings, status=status, launcher=launched.append)

    assert len(launched) == 1
    assert (tmp_path / "runtime" / "lightroom_required_message.json").is_file()


def test_runner_does_not_start_worker_when_lightroom_is_missing(tmp_path, monkeypatch) -> None:
    settings = Settings(runtime_dir=tmp_path / "runtime", lightroom_backend="lightroom")

    @contextmanager
    def fake_session_scope(_settings):
        yield object()

    class FakeTaskRepository:
        def list_by_status(self, _session, _status):
            return [object()]

    class ForbiddenWorker:
        def process_next_queued(self):
            raise AssertionError("worker must not start before Lightroom Classic is running")

    monkeypatch.setattr(runner_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(runner_module, "ImageTaskRepository", FakeTaskRepository)
    monkeypatch.setattr(
        runner_module,
        "lightroom_classic_status",
        lambda _settings: LightroomProcessStatus(
            required=True,
            running=False,
            process_names=("Lightroom.exe",),
            reason=LIGHTROOM_CLASSIC_NOT_RUNNING,
            message="Start Lightroom Classic.",
        ),
    )

    result = AgentRunner(settings=settings, worker=ForbiddenWorker()).run_once(scan_input=False)

    assert result.worker_result is None
    assert result.blocked_reason == LIGHTROOM_CLASSIC_NOT_RUNNING
