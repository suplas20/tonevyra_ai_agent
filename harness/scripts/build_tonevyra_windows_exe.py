"""Build the Windows TonevyraAI.exe tray launcher."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    pyinstaller = shutil.which("pyinstaller")
    if pyinstaller is None:
        print("PyInstaller is required to build TonevyraAI.exe.", file=sys.stderr)
        return 2

    icon_path = project_root / "resources" / "branding" / "windows" / "tonevyra_tray.ico"
    entry_path = project_root / "src" / "tonevyra_agent" / "windows" / "app_entry.py"
    dist_path = project_root / "runtime" / "windows_dist"
    work_path = project_root / "runtime" / "build" / "pyinstaller"

    command = [
        pyinstaller,
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "TonevyraAI",
        "--icon",
        str(icon_path),
        "--paths",
        str(project_root / "src"),
        "--paths",
        str(project_root / ".venv" / "Lib" / "site-packages"),
        "--collect-submodules",
        "tonevyra_agent",
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
