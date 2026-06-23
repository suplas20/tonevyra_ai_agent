#!/usr/bin/env python3
"""Static and optional strict evidence verifier for T025."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any

TICKET = "T025"
REQUIRED_SKILLS = {'user-style-profile', 'personalization-feedback-policy'}
REQUIRED_FILES = ['harness/CONTRACT_T025_USER_STYLE_PERSONALIZATION.md', 'harness/HARNESS_ENV_T025_USER_STYLE_PERSONALIZATION.example', 'harness/schemas/t025_style_profile.schema.json', 'harness/schemas/t025_style_application_evidence.schema.json']
FIXTURE_DIR = "t025_personalization"
FORBIDDEN_KEYS = {'plugin_command', 'external_upload', 'develop_settings', 'auto_model_finetune', 'preset_path'}
REQUIRED_BASELINE_SKILL_COUNT = 33
EXPECTED_TOTAL_SKILL_COUNT = 35
RUNTIME_SCHEMA = "t025.runtime.evidence.v1"


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
        elif path.name in {'valid_style_profile.json', 'valid_style_application.json'}:
            forbidden = find_forbidden(data)
            if forbidden:
                failures.append(f"valid fixture contains forbidden keys {path.name}: {forbidden}")
    failures.extend(ticket_specific(root, fixture_root))
    return failures


def ticket_specific(root: Path, fixture_root: Path) -> list[str]:
    failures = []
    profile = load_json(fixture_root / 'valid_style_profile.json')
    if profile.get('status') != 'ACTIVE' or profile.get('version', 0) < 1:
        failures.append('valid profile must be active and versioned')
    opt_out = load_json(fixture_root / 'opt_out_case.json')
    if opt_out.get('expected_profile_loaded') is not False or opt_out.get('expected_feedback_collected') is not False:
        failures.append('opt-out must disable load and collection')
    isolation = load_json(fixture_root / 'cross_user_isolation_case.json')
    if isolation.get('expected_access') != 'DENY':
        failures.append('cross-user profile access must be denied')
    feedback = load_json(fixture_root / 'feedback_calibration_case.json')
    if feedback.get('automatic_model_finetune') is not False:
        failures.append('automatic model fine-tuning must be false')
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
