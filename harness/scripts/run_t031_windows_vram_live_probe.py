#!/usr/bin/env python3
"""Collect Windows GPU process evidence for T-031.

This script does not claim strict completion by itself. The manual/live idle
unload sequence still has to prove the loaded and post-unload points.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tonevyra_agent.core.config import get_settings  # noqa: E402
from tonevyra_agent.inference.memory_telemetry import collect_windows_gpu_telemetry  # noqa: E402


def main() -> int:
    out = ROOT / "runtime" / "evidence" / "t031" / "windows_vram_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    telemetry = collect_windows_gpu_telemetry()
    blocked_reasons: list[str] = []
    if telemetry.error:
        blocked_reasons.append("NVIDIA_SMI_PROBE_FAILED")
    blocked_reasons.append("MANUAL_WORKER_IDLE_UNLOAD_SEQUENCE_REQUIRED")
    data = {
        "ticket": "T-031",
        "os": "windows" if sys.platform == "win32" else sys.platform,
        "gpu": telemetry.gpu_name or "unknown",
        "worker": {
            "max_concurrent": settings.max_inference_workers,
            "exited_after_idle": False,
        },
        "vram": {
            "loaded_mb": 0,
            "post_unload_mb": 0,
            "threshold_mb": settings.memory_release_threshold_mb,
        },
        "nvidia_process_rows": [row.__dict__ for row in telemetry.rows],
        "strict_completion": False,
        "blocked_reasons": blocked_reasons,
        "error": telemetry.error,
    }
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0 if not telemetry.error else 1


if __name__ == "__main__":
    raise SystemExit(main())

