#!/usr/bin/env python3
"""Static, runtime, and strict Windows evidence verifier for T-030."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

TICKET = "T030"
RUNTIME_SCHEMA = "t030.runtime.evidence.v1"
LIVE_SCHEMA = "t030.windows_live_evidence.v1"
BASELINE_SKILL_COUNT = 43
EXPECTED_SKILL_COUNT = 45
REQUIRED_SKILLS = {
    "windows-background-agent-lifecycle",
    "system-tray-operations",
}
REQUIRED_FILES = [
    ".docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md",
    ".docs/t030/T-030_Implementation_Specification.md",
    ".docs/t030/T-030_Codex_Prompt.md",
    ".docs/t030/T-030_Windows_Live_Test_Checklist.md",
    ".docs/t030/T-030_Tray_Icon_Asset_Guide.md",
    "harness/CONTRACT_T030_WINDOWS_BACKGROUND_TRAY.md",
    "harness/HARNESS_ENV_T030_WINDOWS_BACKGROUND_TRAY.example",
    "harness/schemas/t030_agent_runtime_snapshot.schema.json",
    "harness/schemas/t030_watch_event.schema.json",
    "harness/schemas/t030_tray_command.schema.json",
    "harness/schemas/t030_runtime_evidence.schema.json",
    "harness/schemas/t030_windows_live_evidence.schema.json",
    "harness/fixtures/t030_background_tray/valid_agent_runtime_snapshot.json",
    "harness/fixtures/t030_background_tray/copy_in_progress_stability_case.json",
    "harness/fixtures/t030_background_tray/duplicate_event_coalescing_case.json",
    "harness/fixtures/t030_background_tray/pause_resume_case.json",
    "harness/fixtures/t030_background_tray/restart_recovery_case.json",
    "harness/fixtures/t030_background_tray/single_instance_case.json",
    "harness/fixtures/t030_background_tray/tray_state_mapping_case.json",
    "harness/fixtures/t030_background_tray/graceful_shutdown_case.json",
    "skills/T030_SKILL_INVENTORY.json",
]
FORBIDDEN_TRUE_KEYS = {
    "source_overwrite",
    "source_delete_after_success",
    "second_instance_processes_jobs",
    "ui_business_logic",
    "tray_directly_writes_adjustment_plan",
    "process_before_stable",
    "uses_windows_service",
    "sqlite_queue",
    "unbounded_restart",
}
LIVE_TRUE_FIELDS = [
    "tray_icon_asset_approved",
    "tray_visible",
    "single_instance_passed",
    "copy_in_progress_blocked",
    "deduplication_passed",
    "pause_resume_passed",
    "worker_crash_recovery_passed",
    "no_duplicate_external_effects",
    "graceful_shutdown_passed",
    "no_orphan_processes",
    "source_integrity_passed",
    "regressions_passed",
    "completed",
]
RUNTIME_CHECKS = [
    "file_stability",
    "event_coalescing",
    "deduplication",
    "pause_resume",
    "single_instance",
    "worker_recovery",
    "graceful_shutdown",
    "source_integrity",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_forbidden_true(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and child is True:
                found.append(location)
            found.extend(find_forbidden_true(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_true(child, f"{prefix}[{index}]"))
    return found


def validate_static(root: Path) -> list[str]:
    failures: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing required file: {relative}")

    skill_dirs = {p.parent.name for p in (root / "skills").glob("*/SKILL.md")}
    if len(skill_dirs) < BASELINE_SKILL_COUNT:
        failures.append(f"baseline skill count too small: {len(skill_dirs)} < {BASELINE_SKILL_COUNT}")
    if len(skill_dirs) != EXPECTED_SKILL_COUNT:
        failures.append(f"expected exactly {EXPECTED_SKILL_COUNT} skills, found {len(skill_dirs)}")
    missing_skills = sorted(REQUIRED_SKILLS - skill_dirs)
    if missing_skills:
        failures.append(f"missing T-030 skills: {missing_skills}")

    inventory_path = root / "skills" / "T030_SKILL_INVENTORY.json"
    if inventory_path.is_file():
        inventory = load_json(inventory_path)
        if inventory.get("baseline_skill_count") != BASELINE_SKILL_COUNT:
            failures.append("T030 inventory baseline_skill_count mismatch")
        if inventory.get("expected_total_skill_count") != EXPECTED_SKILL_COUNT:
            failures.append("T030 inventory expected_total_skill_count mismatch")
        if set(inventory.get("all_skills", [])) != skill_dirs:
            failures.append("T030 inventory all_skills does not match actual skill directories")

    fixture_root = root / "harness" / "fixtures" / "t030_background_tray"
    if not fixture_root.is_dir():
        failures.append("missing T-030 fixture directory")
        return failures

    for path in sorted(fixture_root.glob("*.json")):
        try:
            data = load_json(path)
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append(f"invalid JSON {path.name}: {exc}")
            continue
        forbidden = find_forbidden_true(data)
        if path.name.startswith("invalid_"):
            if data.get("expected_validation") != "FAIL":
                failures.append(f"negative fixture must declare FAIL: {path.name}")
            if not forbidden and path.name != "invalid_output_recursive_watch_case.json":
                failures.append(f"negative fixture lacks forbidden marker: {path.name}")
        elif forbidden:
            failures.append(f"valid fixture contains forbidden true key {path.name}: {forbidden}")

    stable = load_json(fixture_root / "copy_in_progress_stability_case.json")
    if stable.get("analysis_may_start_before_stable") is not False:
        failures.append("copy-in-progress fixture must forbid analysis before stability")
    samples = stable.get("samples", [])
    if len(samples) < stable.get("required_stable_samples", 0):
        failures.append("copy-in-progress fixture lacks enough samples")

    duplicate = load_json(fixture_root / "duplicate_event_coalescing_case.json")
    if duplicate.get("expected_task_registrations") != 1:
        failures.append("duplicate event case must register one task")
    if duplicate.get("expected_external_pipeline_executions") != 1:
        failures.append("duplicate event case must execute pipeline once")

    single = load_json(fixture_root / "single_instance_case.json")
    if single.get("second_worker_started") is not False:
        failures.append("second instance must not start another worker")
    if single.get("expected_processing_workers") != 1:
        failures.append("single instance case must expect one processing worker")

    restart = load_json(fixture_root / "restart_recovery_case.json")
    if restart.get("tray_remains_alive") is not True:
        failures.append("tray must remain alive when worker crashes")
    if restart.get("expected_duplicate_external_effects") != 0:
        failures.append("worker recovery must not duplicate external effects")

    shutdown = load_json(fixture_root / "graceful_shutdown_case.json")
    if shutdown.get("expected_orphan_processes") != 0:
        failures.append("graceful shutdown must leave zero orphan processes")
    if shutdown.get("source_modified") is not False:
        failures.append("graceful shutdown case must preserve source")

    contract = (root / "harness" / "CONTRACT_T030_WINDOWS_BACKGROUND_TRAY.md")
    if contract.is_file():
        text = contract.read_text(encoding="utf-8")
        required_phrases = [
            "not a Windows Service",
            "PostgreSQL remains",
            "SQLite fallback is prohibited",
            "no orphan Worker",
            "real Windows live evidence",
        ]
        for phrase in required_phrases:
            if phrase not in text:
                failures.append(f"T-030 contract missing phrase: {phrase}")

    return failures


def validate_runtime(path: Path, strict: bool) -> list[str]:
    failures: list[str] = []
    data = load_json(path)
    if data.get("schema_version") != RUNTIME_SCHEMA:
        failures.append(f"runtime schema_version must be {RUNTIME_SCHEMA}")
    if data.get("ticket") != TICKET:
        failures.append(f"runtime ticket must be {TICKET}")
    if data.get("completed") is not True:
        failures.append("runtime completed must be true")
    if data.get("regressions_passed") is not True:
        failures.append("runtime regressions_passed must be true")
    checks = data.get("checks", {})
    for name in RUNTIME_CHECKS:
        if checks.get(name) is not True:
            failures.append(f"runtime check must pass: {name}")
    if not data.get("evidence"):
        failures.append("runtime evidence list must not be empty")
    if strict and data.get("evidence_source") != "implementation":
        failures.append("strict mode requires evidence_source=implementation")
    return failures


def validate_live(path: Path) -> list[str]:
    failures: list[str] = []
    data = load_json(path)
    if data.get("schema_version") != LIVE_SCHEMA:
        failures.append(f"live schema_version must be {LIVE_SCHEMA}")
    if data.get("ticket") != TICKET:
        failures.append(f"live ticket must be {TICKET}")
    if data.get("platform") != "Windows":
        failures.append("live platform must be Windows")
    for name in LIVE_TRUE_FIELDS:
        if data.get(name) is not True:
            failures.append(f"live evidence field must be true: {name}")
    if not data.get("implementation_build") or data.get("implementation_build") == "<fill>":
        failures.append("live implementation_build must be concrete")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--runtime-evidence", type=Path)
    parser.add_argument("--live-evidence", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    failures = validate_static(root)
    if args.runtime_evidence:
        failures.extend(validate_runtime(args.runtime_evidence.resolve(), args.strict))
    elif args.strict:
        failures.append("strict mode requires --runtime-evidence")

    if args.live_evidence:
        failures.extend(validate_live(args.live_evidence.resolve()))
    elif args.strict:
        failures.append("strict mode requires --live-evidence")

    if failures:
        print(f"FAIL: {TICKET}")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"PASS: {TICKET} static contract and fixtures")
    if args.runtime_evidence:
        print(f"PASS: {TICKET} runtime evidence")
    if args.live_evidence:
        print(f"PASS: {TICKET} Windows live evidence")
    if args.strict:
        print(f"PASS: {TICKET} strict completion gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
