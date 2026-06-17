#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "harness" / "fixtures" / "lightroom_plugin"
ALLOWED_SETTINGS = {
    "exposure", "contrast", "highlights", "shadows", "whites", "blacks",
    "temp", "tint", "vibrance", "saturation", "texture", "clarity", "dehaze",
    "sharpening", "noise_reduction",
}
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
                    raise ValueError(f"banned selected-photo key present: {k}")
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)

def validate_request(obj):
    check_no_banned(obj)
    if require(obj, "schema_version") != "t019.lightroom_apply.request.v1":
        raise ValueError("invalid apply request schema_version")
    if require(obj, "request_origin") != "tonevyra_agent":
        raise ValueError("apply request must originate from tonevyra_agent")
    if require(obj, "command") != "APPLY_LIGHTROOM_SETTINGS":
        raise ValueError("invalid apply request command")
    for field in ["request_id", "task_id", "source_path", "created_at", "develop_settings", "safety.non_destructive_required"]:
        require(obj, field)
    if obj["safety"]["non_destructive_required"] is not True:
        raise ValueError("non_destructive_required must be true")
    settings = require(obj, "develop_settings")
    if not isinstance(settings, dict) or not settings:
        raise ValueError("develop_settings must be a non-empty object")
    unsupported = set(settings) - ALLOWED_SETTINGS
    if unsupported:
        raise ValueError(f"unsupported develop setting in request: {sorted(unsupported)}")

def validate_result(obj):
    check_no_banned(obj)
    if require(obj, "schema_version") != "t019.lightroom_apply.result.v1":
        raise ValueError("invalid apply result schema_version")
    if require(obj, "request_origin") != "lightroom_plugin":
        raise ValueError("apply result must originate from lightroom_plugin")
    if require(obj, "command") != "APPLY_LIGHTROOM_SETTINGS":
        raise ValueError("invalid apply result command")
    status = require(obj, "status")
    if status not in {"applied", "partial", "failed"}:
        raise ValueError("status must be applied, partial, or failed")
    for field in ["request_id", "task_id", "source_path", "applied_settings", "skipped_settings", "lightroom_result.worker_running"]:
        require(obj, field)
    if status in {"applied", "partial"}:
        if not require(obj, "lightroom_result.develop_settings_applied"):
            raise ValueError("successful result must set develop_settings_applied=true")
    if status == "applied" and not obj["applied_settings"]:
        raise ValueError("applied status requires non-empty applied_settings")
    if status == "failed":
        for field in ["error.code", "error.message", "error.recoverable"]:
            require(obj, field)

def load(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

def main():
    try:
        validate_request(load("valid_apply_request.json"))
        validate_result(load("valid_apply_result.json"))
        validate_result(load("failed_apply_result.json"))
        try:
            validate_request(load("invalid_lightroom_origin_flow.json"))
        except Exception:
            pass
        else:
            return fail("invalid selected-photo flow fixture unexpectedly passed")
    except Exception as exc:
        return fail(str(exc))
    print("OK folder-driven Lightroom bridge contract fixtures are valid")
    return 0

if __name__ == "__main__":
    sys.exit(main())
