#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "harness" / "fixtures" / "lightroom_plugin" / "valid_apply_result.json"
BANNED_KEYS = {"selected" + "_count", "selected" + "_photo_detected"}

def fail(msg: str) -> int:
    print(f"FAIL {msg}")
    return 1

def require(obj, path: str):
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            raise ValueError(f"missing required field: {path}")
        cur = cur[part]
    return cur

def check_no_banned(obj):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in BANNED_KEYS:
                    raise ValueError(f"banned selected-photo evidence key present: {k}")
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)

def validate_evidence(obj):
    check_no_banned(obj)
    if require(obj, "schema_version") != "t019.lightroom_apply.result.v1":
        raise ValueError("expected t019.lightroom_apply.result.v1")
    if require(obj, "request_origin") != "lightroom_plugin":
        raise ValueError("apply result must originate from lightroom_plugin")
    if require(obj, "command") != "APPLY_LIGHTROOM_SETTINGS":
        raise ValueError("invalid command")
    for field in ["request_id", "task_id", "source_path", "status", "applied_settings", "skipped_settings", "lightroom_result.plugin_loaded", "lightroom_result.worker_running"]:
        require(obj, field)
    status = obj["status"]
    if status not in {"applied", "partial", "failed"}:
        raise ValueError("invalid status")
    lr = obj["lightroom_result"]
    if status in {"applied", "partial"}:
        if not lr.get("worker_running"):
            raise ValueError("worker_running must be true for applied/partial")
        if not (lr.get("source_photo_found") or lr.get("source_photo_imported")):
            raise ValueError("source_photo_found or source_photo_imported must be true")
        if not lr.get("develop_settings_applied"):
            raise ValueError("develop_settings_applied must be true")
        if not obj["applied_settings"]:
            raise ValueError("applied/partial result requires non-empty applied_settings")
    if status == "failed":
        for field in ["error.code", "error.message", "error.recoverable"]:
            require(obj, field)

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate T-019 folder-driven Lightroom live test evidence JSON.")
    parser.add_argument("--evidence", default=str(DEFAULT_FIXTURE), help="Path to apply result/live evidence JSON")
    args = parser.parse_args()
    path = Path(args.evidence)
    if not path.exists():
        return fail(f"evidence file does not exist: {path}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        validate_evidence(obj)
    except Exception as exc:
        return fail(str(exc))
    print(f"OK folder-driven Lightroom live test evidence is valid: {path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
