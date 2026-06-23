#!/usr/bin/env python3
"""Static and optional strict evidence verifier for T028."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any

TICKET = "T028"
REQUIRED_SKILLS = {'production-reliability-operations', 'resumable-idempotent-jobs'}
REQUIRED_FILES = ['harness/CONTRACT_T028_PRODUCTION_RELIABILITY_OPERATIONS.md', 'harness/HARNESS_ENV_T028_PRODUCTION_RELIABILITY_OPERATIONS.example', 'harness/schemas/t028_operation_checkpoint.schema.json', 'harness/schemas/t028_incident_event.schema.json']
FIXTURE_DIR = "t028_operations"
FORBIDDEN_KEYS = {'unbounded_retry_allowed', 'overwrite_trusted_artifact', 'skip_idempotency'}
REQUIRED_BASELINE_SKILL_COUNT = 39
EXPECTED_TOTAL_SKILL_COUNT = 41
RUNTIME_SCHEMA = "t028.runtime.evidence.v1"


def load_json(path: Path) -> Any:
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def find_forbidden(value: Any, prefix: str = '$') -> list[str]:
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{prefix}.{k}"
            if k in FORBIDDEN_KEYS:
                found.append(p)
            found.extend(find_forbidden(v, p))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found.extend(find_forbidden(v, f"{prefix}[{i}]"))
    return found


def validate_ticket(root: Path) -> list[str]:
    failures = []
    skill_dirs = {p.parent.name for p in (root / 'skills').glob('*/SKILL.md')}
    if len(skill_dirs) < REQUIRED_BASELINE_SKILL_COUNT:
        failures.append(f"baseline skill count too small: {len(skill_dirs)}")
    missing_skills = sorted(REQUIRED_SKILLS - skill_dirs)
    if missing_skills:
        failures.append(f"missing skills: {missing_skills}")
    if len(skill_dirs) < EXPECTED_TOTAL_SKILL_COUNT:
        failures.append(f"expected at least cumulative skill count {EXPECTED_TOTAL_SKILL_COUNT}, found {len(skill_dirs)}")
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            failures.append(f"missing required file: {rel}")
    fixture_root = root / 'harness' / 'fixtures' / FIXTURE_DIR
    if not fixture_root.is_dir():
        failures.append(f"missing fixture dir: {fixture_root}")
        return failures
    for path in sorted(fixture_root.glob('*.json')):
        try:
            data = load_json(path)
        except Exception as e:
            failures.append(f"invalid JSON {path.name}: {e}")
            continue
        if path.name.startswith('invalid_') or path.name.startswith('unsubstantiated_'):
            if not find_forbidden(data) and data.get('expected_validation') != 'FAIL':
                failures.append(f"negative fixture has no detectable invalid marker: {path.name}")
        elif path.name in {'valid_checkpoint.json', 'valid_incident_event.json'}:
            forbidden = find_forbidden(data)
            if forbidden:
                failures.append(f"valid fixture contains forbidden keys {path.name}: {forbidden}")
    failures.extend(ticket_specific(root, fixture_root))
    return failures


def ticket_specific(root: Path, fixture_root: Path) -> list[str]:
    failures = []
    duplicate = load_json(fixture_root / 'duplicate_command_case.json')
    if duplicate.get('expected_external_executions') != 1:
        failures.append('duplicate command must execute externally once')
    stale = load_json(fixture_root / 'stale_lease_case.json')
    if stale.get('expected_action') != 'RECLAIM' or stale.get('owner_process_alive') is not False:
        failures.append('stale lease fixture must support safe reclaim')
    timeout = load_json(fixture_root / 'timeout_policy.json')
    if timeout.get('unbounded_retry_allowed') is not False:
        failures.append('unbounded retry must be false')
    usage = load_json(fixture_root / 'usage_exactly_once_case.json')
    if usage.get('expected_commits') != 1:
        failures.append('usage commit must be exactly-once in effect')
    audit = load_json(fixture_root / 'operator_action_audit_case.json')
    if not all(audit.get(k) is True for k in ('dry_run_supported','confirmation_required','audit_event_required')):
        failures.append('operator action safety/audit requirements missing')
    return failures


def validate_runtime_evidence(path: Path) -> list[str]:
    failures = []
    data = load_json(path)
    if data.get('schema_version') != RUNTIME_SCHEMA:
        failures.append(f"runtime evidence schema_version must be {RUNTIME_SCHEMA}")
    if data.get('ticket') != TICKET:
        failures.append(f"runtime evidence ticket must be {TICKET}")
    if data.get('completed') is not True:
        failures.append('runtime evidence completed must be true')
    if data.get('regressions_passed') is not True:
        failures.append('runtime evidence regressions_passed must be true')
    if not data.get('evidence'):
        failures.append('runtime evidence must include evidence entries')
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--runtime-evidence', type=Path)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    failures = validate_ticket(args.project_root)
    if args.runtime_evidence:
        failures.extend(validate_runtime_evidence(args.runtime_evidence))
    elif args.strict:
        failures.append('--strict requires --runtime-evidence from a real implementation run')
    if failures:
        print(f"FAIL: {TICKET}")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"PASS: {TICKET} static contract and fixtures")
    if args.runtime_evidence:
        print(f"PASS: {TICKET} runtime evidence")
    return 0

if __name__ == '__main__':
    sys.exit(main())
