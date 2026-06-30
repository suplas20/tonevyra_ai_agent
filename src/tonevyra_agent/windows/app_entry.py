"""Windows executable entry point for Tonevyra AI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _configure_project_root() -> None:
    if os.environ.get("TONEVYRA_PROJECT_ROOT") or not getattr(sys, "frozen", False):
        return
    executable = Path(sys.executable).resolve()
    try:
        project_root = executable.parents[3]
    except IndexError:
        return
    if (project_root / "AGENTS.md").exists():
        os.environ["TONEVYRA_PROJECT_ROOT"] = str(project_root)


def main() -> None:
    _configure_project_root()
    from tonevyra_agent.cli import app

    if len(sys.argv) == 1:
        sys.argv.append("tray")
    app(prog_name="TonevyraAI")


if __name__ == "__main__":
    main()
