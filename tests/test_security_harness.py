from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_security_harness_script_runs() -> None:
    script = ROOT / "harness" / "scripts" / "run_security_check.py"
    result = subprocess.run([sys.executable, str(script), "--root", str(ROOT)], cwd=ROOT)
    assert result.returncode == 0
