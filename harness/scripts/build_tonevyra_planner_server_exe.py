"""Build the standalone Windows Tonevyra Planner Server executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path(os.environ.get("TONEVYRA_WINDOWS_INSTALLER_OUTPUT_DIR", r"D:\Tonevyra_install")) / "TonevyraPlannerServer"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sign", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = args.output_dir.expanduser().resolve()
    work_dir = project_root / "runtime" / "build" / "planner_server_pyinstaller"
    output_dir.mkdir(parents=True, exist_ok=True)
    entry = project_root / "src" / "tonevyra_planner_service" / "main.py"
    icon = project_root / "resources" / "branding" / "windows" / "tonevyra_tray.ico"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "TonevyraPlannerServer",
        "--icon",
        str(icon),
        "--paths",
        str(project_root / "src"),
        "--collect-submodules",
        "tonevyra_planner_service",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--exclude-module",
        "torch",
        "--exclude-module",
        "transformers",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        str(entry),
    ]
    result = subprocess.run(command, cwd=project_root, check=False)
    if result.returncode != 0:
        return result.returncode
    exe = output_dir / "TonevyraPlannerServer.exe"
    if not exe.is_file():
        raise SystemExit(f"planner server executable missing: {exe}")
    if args.sign:
        sign_script = project_root / "installer" / "windows" / "Sign-Tonevyra.ps1"
        sign = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sign_script), "-Files", str(exe)],
            cwd=project_root,
            check=False,
        )
        if sign.returncode != 0:
            return sign.returncode
    manifest = {
        "schema_version": "tonevyra.planner_server.windows.v1",
        "executable": str(exe),
        "sha256": _sha256(exe),
        "size_bytes": exe.stat().st_size,
        "bind_host": "127.0.0.1",
        "port": 8000,
        "local_test_only": True,
        "signed": args.sign,
    }
    manifest_path = output_dir / "TonevyraPlannerServer.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OK: planner_server={exe}")
    print(f"OK: manifest={manifest_path}")
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
