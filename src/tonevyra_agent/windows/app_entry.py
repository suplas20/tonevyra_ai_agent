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


def main() -> None:
    _configure_project_root()
    if len(sys.argv) > 1 and sys.argv[1] == "inference-worker":
        from tonevyra_agent.inference.worker_process import main as worker_main

        raise SystemExit(worker_main(["run", *sys.argv[2:]]))
    from tonevyra_agent.cli import app

    if len(sys.argv) == 1:
        sys.argv.append("tray")
    app(prog_name="TonevyraAI")


if __name__ == "__main__":
    main()
