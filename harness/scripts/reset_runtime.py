from __future__ import annotations

import argparse
from pathlib import Path
from _common import RUNTIME_DIR, ensure_runtime_dirs, reset_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Tonevyra AI Agent runtime folders for harness runs.")
    parser.add_argument("--runtime-dir", default=str(RUNTIME_DIR), help="Runtime directory. Defaults to TONEVYRA_RUNTIME_DIR, legacy MW_RUNTIME_DIR, or ./runtime")
    parser.add_argument("--keep", action="store_true", help="Only create missing folders; do not clear existing files.")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir).resolve()
    if args.keep:
        ensure_runtime_dirs(runtime_dir)
        print(f"Runtime folders ensured: {runtime_dir}")
    else:
        # Patch module global safety boundary when caller overrides runtime dir.
        import _common
        _common.RUNTIME_DIR = runtime_dir
        reset_runtime(runtime_dir)
        print(f"Runtime reset complete: {runtime_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
