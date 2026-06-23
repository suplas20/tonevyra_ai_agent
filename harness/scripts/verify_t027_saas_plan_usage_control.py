#!/usr/bin/env python3
"""Static and optional strict evidence verifier for T027."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any

TICKET = "T027"
REQUIRED_SKILLS = {'saas-plan-routing', 'usage-cost-control'}
REQUIRED_FILES = ['harness/CONTRACT_T027_SAAS_PLAN_USAGE_CONTROL.md', 'harness/HARNESS_ENV_T027_SAAS_PLAN_USAGE_CONTROL.example', 'harness/schemas/t027_plan_policy.schema.json', 'harness/schemas/t027_usage_ledger_event.schema.json']
FIXTURE_DIR = "t027_saas_policy"
FORBIDDEN_KEYS = {'intentionally_reduce_quality', 'quality_multiplier', 'silent_module_fallback'}
REQUIRED_BASELINE_SKILL_COUNT = 37
EXPECTED_TOTAL_SKILL_COUNT = 39
RUNTIME_SCHEMA = "t027.runtime.evidence.v1"


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
        elif path.name in {'valid_usage_ledger_event.json', 'plan_policies.json'}:
            forbidden = find_forbidden(data)
            if forbidden:
                failures.append(f"valid fixture contains forbidden keys {path.name}: {forbidden}")
    failures.extend(ticket_specific(root, fixture_root))
    return failures


def ticket_specific(root: Path, fixture_root: Path) -> list[str]:
    failures = []
    policies = load_json(fixture_root / 'plan_policies.json').get('policies', [])
    by_plan = {p.get('plan_id'): p for p in policies}
    for p in ('free','lite'):
        if by_plan.get(p, {}).get('analysis_provider') != 'module' or by_plan.get(p, {}).get('quality_provider') != 'module':
            failures.append(f'{p} must use module providers')
    for p in ('standard','pro'):
        if by_plan.get(p, {}).get('analysis_provider') != 'model' or by_plan.get(p, {}).get('quality_provider') != 'model':
            failures.append(f'{p} must use model providers')
    idem = load_json(fixture_root / 'idempotent_usage_cases.json')
    if idem.get('expected_committed_photo_units') != 1:
        failures.append('duplicate usage events must commit one photo unit')
    retry = load_json(fixture_root / 'retry_accounting_case.json')
    if retry.get('expected_photo_units') != 1:
        failures.append('quality retries must not double-count photo units')
    fail_closed = load_json(fixture_root / 'fail_closed_case.json')
    if fail_closed.get('expected_route') != 'DENY':
        failures.append('missing policy must fail closed')
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
