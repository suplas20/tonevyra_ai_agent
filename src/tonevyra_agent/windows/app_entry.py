"""Windows executable entry point for Tonevyra AI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _configure_project_root() -> None:
    if os.environ.get("TONEVYRA_PROJECT_ROOT") or not getattr(sys, "frozen", False):
        return
    executable = Path(sys.executable).resolve()
    candidates = [executable.parent]
    candidates.extend(executable.parents[:4])
    for project_root in candidates:
        if (project_root / "AGENTS.md").exists() or (project_root / "resources" / "branding").exists():
            os.environ["TONEVYRA_PROJECT_ROOT"] = str(project_root)
            return
    os.environ["TONEVYRA_PROJECT_ROOT"] = str(executable.parent)


def _notify_planner_startup_issue() -> None:
    from tonevyra_agent.core.config import get_settings
    from tonevyra_agent.core.enums import ErrorCode, Stage
    from tonevyra_agent.core.errors import TonevyraError
    from tonevyra_agent.planner_api.client import PlannerApiClient
    from tonevyra_agent.planner_api.user_messages import planner_error_message
    from tonevyra_agent.windows.user_notifications import show_error_message

    settings = get_settings()
    if (settings.planner_api_mode or "api").lower() == "local_test":
        return
    try:
        PlannerApiClient(settings).check_readiness()
    except TonevyraError as exc:
        show_error_message("Tonevyra AI - 플래너 서버 오류", planner_error_message(exc))
    except Exception as exc:
        error = TonevyraError(
            code=ErrorCode.PLANNER_API_UNAVAILABLE,
            message=f"Planner readiness check failed: {exc}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
        show_error_message("Tonevyra AI - 플래너 서버 오류", planner_error_message(error))


def main() -> None:
    _configure_project_root()
    if len(sys.argv) > 1 and sys.argv[1] == "inference-worker":
        from tonevyra_agent.inference.worker_process import main as worker_main

        raise SystemExit(worker_main(["run", *sys.argv[2:]]))
    launches_tray = len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] == "tray")
    if launches_tray:
        _notify_planner_startup_issue()
    from tonevyra_agent.cli import app

    if len(sys.argv) == 1:
        sys.argv.append("tray")
    app(prog_name="TonevyraAI")


if __name__ == "__main__":
    main()
