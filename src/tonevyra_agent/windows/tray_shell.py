"""Thin T-030 system tray shell boundary.

The shell is intentionally a status renderer and command client. It does not own
planner, Lightroom, quality, or DB pipeline logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from tonevyra_agent.agent.background_runtime import write_tray_command
from tonevyra_agent.agent.runtime_snapshot import RuntimeSnapshotStore
from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.windows.background_launcher import BackgroundWorkerLauncher
from tonevyra_agent.windows.shell_worker_ipc import TrayCommand, TrayCommandName
from tonevyra_agent.windows.single_instance import SingleInstanceGuard, per_user_mutex_name
from tonevyra_agent.windows.native_tray import NativeTrayIcon
from tonevyra_agent.windows.tray_icons import tray_icon_status


@dataclass
class TrayShell:
    settings: Settings | None = None
    shell_instance_id: str = "tray-shell"

    def run(self, *, probe_seconds: float | None = None, start_background: bool = True) -> int:
        """Start the tray shell boundary.

        The shell owns only status rendering and command dispatch. It never
        owns the photo pipeline, planner, Lightroom bridge, quality gate, or DB
        mutations.
        """

        config = self.settings or get_settings()
        with SingleInstanceGuard(per_user_mutex_name("Tray"), config) as guard:
            if not guard.acquired:
                return 0
            icon_status = tray_icon_status()
            if not icon_status.production_ready:
                RuntimeSnapshotStore(config).read()
                return 2
            launcher = BackgroundWorkerLauncher(config)
            if start_background:
                launcher.start()
            icon_path = icon_status.icons["tonevyra_tray.ico"]
            tray = NativeTrayIcon(icon_path, tooltip="Tonevyra AI")
            try:
                if probe_seconds is not None:
                    result = tray.show_for(probe_seconds)
                else:
                    result = tray.run_until_interrupted()
            finally:
                if start_background:
                    launcher.stop()
            if result.added and result.removed and result.error_code is None:
                return 0
            return 2

    def send_command(self, command: TrayCommandName) -> None:
        write_tray_command(TrayCommand(command=command, source="TRAY"), self.settings or get_settings())
