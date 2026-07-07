"""Lightroom Classic process preflight for real bridge execution."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tonevyra_agent.core.config import Settings, get_settings


LIGHTROOM_CLASSIC_NOT_RUNNING = "LIGHTROOM_CLASSIC_NOT_RUNNING"


@dataclass(frozen=True)
class LightroomProcessStatus:
    required: bool
    running: bool
    process_names: tuple[str, ...]
    reason: str | None = None
    message: str | None = None


ProcessChecker = Callable[[str], bool]


def lightroom_classic_status(
    settings: Settings | None = None,
    *,
    process_checker: ProcessChecker | None = None,
) -> LightroomProcessStatus:
    """Return whether Lightroom Classic is available before model work starts."""

    config = settings or get_settings()
    names = _configured_process_names(config)
    if config.lightroom_backend != "lightroom":
        return LightroomProcessStatus(required=False, running=True, process_names=names)

    checker = process_checker or _process_exists
    running = any(checker(name) for name in names)
    if running:
        return LightroomProcessStatus(required=True, running=True, process_names=names)

    return LightroomProcessStatus(
        required=True,
        running=False,
        process_names=names,
        reason=LIGHTROOM_CLASSIC_NOT_RUNNING,
        message=(
            "Lightroom Classic is not running. Start Lightroom Classic with "
            "the TonevyraAI.lrplugin enabled, then Tonevyra will continue."
        ),
    )


def record_lightroom_required_message(
    settings: Settings | None = None,
    *,
    status: LightroomProcessStatus | None = None,
    notify: bool = True,
    launcher: Callable[[list[str]], object] | None = None,
) -> Path:
    """Persist local evidence and show a bounded best-effort user message."""

    config = settings or get_settings()
    current_status = status or lightroom_classic_status(config)
    runtime_dir = config.project_path(config.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = runtime_dir / "lightroom_required_message.json"
    now = time.time()
    payload = {
        "schema_version": "tonevyra.lightroom_required_message.v1",
        "reason": current_status.reason or LIGHTROOM_CLASSIC_NOT_RUNNING,
        "message": current_status.message,
        "process_names": list(current_status.process_names),
        "created_at_epoch": now,
        "notification_attempted": False,
    }

    if notify and _notification_allowed(path, now, config.lightroom_missing_notification_cooldown_seconds):
        payload["notification_attempted"] = _show_windows_message(current_status, launcher=launcher)

    _atomic_write_json(path, payload)
    return path


def _configured_process_names(settings: Settings) -> tuple[str, ...]:
    names = tuple(
        name.strip()
        for name in settings.lightroom_classic_process_names.split(",")
        if name.strip()
    )
    return names or ("Lightroom.exe",)


def _process_exists(process_name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    return process_name.lower() in result.stdout.lower()


def _notification_allowed(path: Path, now: float, cooldown_seconds: float) -> bool:
    if not path.exists():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        created_at = float(payload.get("created_at_epoch", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return True
    return now - created_at >= cooldown_seconds


def _show_windows_message(
    status: LightroomProcessStatus,
    *,
    launcher: Callable[[list[str]], object] | None = None,
) -> bool:
    if os.name != "nt":
        return False
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _message_box_script(status.message or "Please start Lightroom Classic."),
    ]
    try:
        if launcher is not None:
            launcher(command)
        else:
            subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        return False
    return True


def _message_box_script(message: str) -> str:
    escaped = message.replace("'", "''")
    return (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[System.Windows.Forms.MessageBox]::Show("
        f"'{escaped}',"
        "'Tonevyra AI',"
        "[System.Windows.Forms.MessageBoxButtons]::OK,"
        "[System.Windows.Forms.MessageBoxIcon]::Warning"
        ") | Out-Null"
    )


def _atomic_write_json(path: Path, payload: dict) -> None:
    temp_path: Path | None = None
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)
