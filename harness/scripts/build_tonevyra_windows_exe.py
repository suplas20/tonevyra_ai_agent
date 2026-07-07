"""Build the Windows TonevyraAI.exe tray launcher."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]

    icon_path = project_root / "resources" / "branding" / "windows" / "tonevyra_tray.ico"
    entry_path = project_root / "src" / "tonevyra_agent" / "windows" / "app_entry.py"
    dist_path = project_root / "runtime" / "windows_dist"
    work_path = project_root / "runtime" / "build" / "pyinstaller"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "TonevyraAI",
        "--icon",
        str(icon_path),
        "--paths",
        str(project_root / "src"),
        "--collect-submodules",
        "tonevyra_agent",
        "--exclude-module",
        "tonevyra_planner_service",
        "--exclude-module",
        "tonevyra_agent.correction.planner",
        "--exclude-module",
        "tonevyra_agent.correction.target_based",
        "--exclude-module",
        "torch",
        "--exclude-module",
        "torchvision",
        "--exclude-module",
        "transformers",
        "--exclude-module",
        "sentence_transformers",
        "--exclude-module",
        "scipy",
        "--exclude-module",
        "pandas",
        "--exclude-module",
        "pyarrow",
        "--exclude-module",
        "sklearn",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "nltk",
        "--distpath",
        str(dist_path),
        "--workpath",
        str(work_path),
        "--specpath",
        str(work_path),
        str(entry_path),
    ]
    return subprocess.run(command, cwd=project_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
