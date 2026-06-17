from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = Path(
    os.environ.get("TONEVYRA_RUNTIME_DIR")
    or os.environ.get("MW_RUNTIME_DIR")  # backward compatibility for older harness envs
    or PROJECT_ROOT / "runtime"
).resolve()

RUNTIME_SUBDIRS = [
    "input",
    "output/pass",
    "output/review_required",
    "output/failed",
    "output/temp",
    "artifacts",
    "previews",
    "bridge/requests",
    "bridge/processing",
    "bridge/responses",
    "bridge/errors",
]

IGNORED_NAMES = {".DS_Store"}
IGNORED_SUFFIXES = {".tmp", ".part", ".crdownload", ".xmp"}


def ensure_runtime_dirs(runtime_dir: Path = RUNTIME_DIR) -> None:
    for subdir in RUNTIME_SUBDIRS:
        (runtime_dir / subdir).mkdir(parents=True, exist_ok=True)


def safe_clear_dir(path: Path, runtime_dir: Path = RUNTIME_DIR) -> None:
    path = path.resolve()
    runtime_root = runtime_dir.resolve()
    try:
        path.relative_to(runtime_root)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to clear path outside runtime: {path}") from exc
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def reset_runtime(runtime_dir: Path = RUNTIME_DIR) -> None:
    runtime_dir = runtime_dir.resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for subdir in RUNTIME_SUBDIRS:
        safe_clear_dir(runtime_dir / subdir, runtime_dir=runtime_dir)


def is_ignored_file(path: Path) -> bool:
    name = path.name
    if name in IGNORED_NAMES:
        return True
    if name.startswith("._") or name.startswith("."):
        return True
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True
    return False


def find_files(root: Path, patterns: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(root.glob(pattern))
    return sorted(files)
