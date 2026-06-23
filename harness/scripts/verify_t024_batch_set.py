#!/usr/bin/env python3
"""Static and optional strict evidence verifier for T024."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any

TICKET = "T024"
REQUIRED_SKILLS = {'batch-photo-processing', 'photo-set-consistency'}
REQUIRED_FILES = ['harness/CONTRACT_T024_BATCH_SET_CONSISTENCY.md', 'harness/HARNESS_ENV_T024_BATCH_SET_CONSISTENCY.example', 'harness/schemas/t024_batch_job.schema.json', 'harness/schemas/t024_set_consistency_result.schema.json']
FIXTURE_DIR = "t024_batch_set"
FORBIDDEN_KEYS = {'shared_attempt_id', 'overwrite_completed', 'unbounded_batch'}
REQUIRED_BASELINE_SKILL_COUNT = 31
EXPECTED_TOTAL_SKILL_COUNT = 33
RUNTIME_SCHEMA = "t024.runtime.evidence.v1"


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
        elif path.name in {'valid_batch_manifest.json', 'valid_set_consistency_result.json'}:
            forbidden = find_forbidden(data)
            if forbidden:
                failures.append(f"valid fixture contains forbidden keys {path.name}: {forbidden}")
    failures.extend(ticket_specific(root, fixture_root))
    return failures


def ticket_specific(root: Path, fixture_root: Path) -> list[str]:
    failures = []
    batch = load_json(fixture_root / 'valid_batch_manifest.json')
    if batch.get('chunk_size') != 10:
        failures.append('default batch chunk_size must be 10')
    ids = [i.get('job_id') for i in batch.get('items', [])]
    keys = [i.get('idempotency_key') for i in batch.get('items', [])]
    if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
        failures.append('batch item ids and idempotency keys must be unique')
    retry = load_json(fixture_root / 'retry_isolation_case.json')
    if retry.get('expected_job_b_count_after_job_a_retry') != retry.get('job_b', {}).get('quality_retry_count'):
        failures.append('retry isolation fixture is inconsistent')
    partial = load_json(fixture_root / 'partial_failure_case.json')
    if partial.get('continue_remaining') is not True:
        failures.append('partial failure must continue remaining items')
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
