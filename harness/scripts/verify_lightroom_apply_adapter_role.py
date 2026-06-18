#!/usr/bin/env python3
"""Verify T-019 Lightroom Apply Adapter role boundaries.

This harness intentionally does not execute Lightroom. It statically checks the
project's T-019 role contract, fixtures, and optional plugin code for boundary
violations.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

REQUIRED_REQUEST_FIELDS = {
    "schema_version", "request_id", "task_id", "source_path", "operation", "created_at"
}
REQUIRED_RESULT_FIELDS = {
    "schema_version", "request_id", "task_id", "source_path", "status", "catalog_action", "completed_at", "message"
}

PROHIBITED_PATTERNS = [
    (re.compile(r"runtime[\\/]+input", re.IGNORECASE), "plugin must not watch or scan runtime/input"),
    (re.compile(r"input[_ -]?folder", re.IGNORECASE), "plugin must not own input folder logic"),
    (re.compile(r"watch(?:er|ing)?[_ -]?(?:folder|input|image)", re.IGNORECASE), "plugin must not implement folder watcher behavior"),
    (re.compile(r"getTargetPhoto\s*\(", re.IGNORECASE), "selected-photo target selection must not be the main workflow"),
    (re.compile(r"selected[_ -]?photo", re.IGNORECASE), "selected-photo product workflow is prohibited"),
    (re.compile(r"RUN_TONEVYRA_CORRECTION", re.IGNORECASE), "manual selected-photo command must not be the main workflow"),
    (re.compile(r"quality[_ -]?score|quality[_ -]?gate", re.IGNORECASE), "plugin must not compute quality gate or score"),
    (re.compile(r"model[_ -]?inference|vision[_ -]?model|qwen|onnx|torch", re.IGNORECASE), "plugin must not invoke AI/model inference"),
    (re.compile(r"correction[_ -]?plan(?:ner)?", re.IGNORECASE), "plugin must not generate correction plans"),
]

REQUIRED_PLUGIN_TERMS = [
    "lightroom_apply_requests",
    "lightroom_apply_results",
    "source_path",
    "request_id",
    "task_id",
    "auto_bridge",
    "diagnostic",
]

IMPLEMENTATION_SUFFIXES = {".lua", ".json", ".txt"}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssertionError(f"Invalid JSON: {path}: {exc}") from exc


def assert_fields(data: dict, required: set[str], path: Path) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise AssertionError(f"{path} missing required fields: {missing}")


def iter_implementation_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() in IMPLEMENTATION_SUFFIXES:
            yield path
        return
    for item in path.rglob("*"):
        if item.is_file() and item.suffix.lower() in IMPLEMENTATION_SUFFIXES:
            yield item


def scan_prohibited(plugin_dir: Path) -> list[str]:
    failures: list[str] = []
    for file in iter_implementation_files(plugin_dir):
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, reason in PROHIBITED_PATTERNS:
            if pattern.search(text):
                failures.append(f"{file}: {reason} ({pattern.pattern})")
    return failures


def scan_required_terms(plugin_dir: Path) -> list[str]:
    combined = []
    for file in iter_implementation_files(plugin_dir):
        try:
            combined.append(file.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    text = "\n".join(combined).lower()
    missing = [term for term in REQUIRED_PLUGIN_TERMS if term.lower() not in text]
    return missing


def scan_diagnostic_menu_boundary(plugin_dir: Path) -> list[str]:
    failures: list[str] = []
    info_path = plugin_dir / "Info.lua"
    process_path = plugin_dir / "ProcessPending.lua"
    info_text = info_path.read_text(encoding="utf-8", errors="ignore") if info_path.exists() else ""
    process_text = process_path.read_text(encoding="utf-8", errors="ignore") if process_path.exists() else ""
    combined = f"{info_text}\n{process_text}".lower()
    if "process pending apply request" in combined and "diagnostic" not in combined:
        failures.append("Manual pending-request menu must be labeled and wired as diagnostic-only")
    return failures


def verify_fixtures(project_root: Path) -> list[str]:
    failures: list[str] = []
    fixture_dir = project_root / "harness" / "fixtures" / "lightroom_apply_adapter"
    if not fixture_dir.exists():
        failures.append(f"Missing fixture directory: {fixture_dir}")
        return failures

    req_path = fixture_dir / "valid_apply_request.json"
    res_path = fixture_dir / "valid_apply_result.json"
    failed_res_path = fixture_dir / "failed_apply_result.json"
    bad_req_path = fixture_dir / "invalid_missing_source_path_request.json"

    for path in [req_path, res_path, failed_res_path, bad_req_path]:
        if not path.exists():
            failures.append(f"Missing fixture: {path}")
            return failures

    try:
        req = load_json(req_path)
        assert_fields(req, REQUIRED_REQUEST_FIELDS, req_path)
        if "develop_settings" not in req and "preset_path" not in req:
            failures.append(f"{req_path} must include develop_settings or preset_path")
        if not req.get("source_path"):
            failures.append(f"{req_path} must include non-empty source_path")

        res = load_json(res_path)
        assert_fields(res, REQUIRED_RESULT_FIELDS, res_path)
        if res.get("status") not in {"applied", "failed", "skipped", "partial"}:
            failures.append(f"{res_path} has invalid status: {res.get('status')}")
        if res.get("status") == "applied" and not (res.get("applied_parameters") or res.get("applied_preset")):
            failures.append(f"{res_path} applied result must include applied_parameters or applied_preset")

        failed_res = load_json(failed_res_path)
        assert_fields(failed_res, REQUIRED_RESULT_FIELDS, failed_res_path)
        if failed_res.get("status") != "failed":
            failures.append(f"{failed_res_path} must be a failed result")
        if not failed_res.get("error_code"):
            failures.append(f"{failed_res_path} must include error_code")

        bad_req = load_json(bad_req_path)
        if bad_req.get("source_path"):
            failures.append(f"{bad_req_path} should intentionally omit source_path")
    except AssertionError as exc:
        failures.append(str(exc))

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Lightroom Apply Adapter role boundary for T-019")
    parser.add_argument("--project-root", default=".", help=r"Project root, e.g. F:\tonevyra_ai_agent")
    parser.add_argument("--plugin-dir", default=None, help="Optional plugin directory to scan")
    parser.add_argument("--strict", action="store_true", help="Fail if plugin-dir is omitted")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    failures: list[str] = []

    contract = project_root / "harness" / "CONTRACT_LIGHTROOM_APPLY_ADAPTER.md"
    skill = project_root / "skills" / "lightroom-apply-adapter" / "SKILL.md"
    if not contract.exists():
        failures.append(f"Missing contract: {contract}")
    if not skill.exists():
        failures.append(f"Missing skill: {skill}")

    failures.extend(verify_fixtures(project_root))

    if args.plugin_dir:
        plugin_dir = Path(args.plugin_dir).resolve()
        if not plugin_dir.exists():
            failures.append(f"Plugin directory does not exist: {plugin_dir}")
        else:
            failures.extend(scan_prohibited(plugin_dir))
            missing = scan_required_terms(plugin_dir)
            if missing:
                failures.append(f"Plugin appears not to implement required adapter terms: {missing}")
            failures.extend(scan_diagnostic_menu_boundary(plugin_dir))
    elif args.strict:
        failures.append("--plugin-dir is required in --strict mode")

    if failures:
        print("FAIL: Lightroom Apply Adapter role verification failed")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PASS: Lightroom Apply Adapter role contract, skill, fixtures, and optional plugin scan passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
