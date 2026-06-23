#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASELINE_SKILLS = {
    "agent-worker-pipeline", "artifact-storage", "cli-operations", "correction-planner",
    "correction-planning", "feedback-learning", "folder-watcher", "image-metadata-preview",
    "lightroom-apply-adapter", "lightroom-bridge", "lightroom-final-export-adapter",
    "lightroom-live-test", "lightroom-plugin-implementation", "local-model-security",
    "loop-engineering", "model-benchmark-loop", "model-security", "postgresql-persistence",
    "project-scope", "python-mvp-structure", "quality-gate", "recovery-error-handling",
    "recovery-loop", "testing-harness", "vision-analysis",
}
NEW_SKILLS = {"dual-mode-agent-core", "closed-loop-quality-reprocessing"}
FORBIDDEN_ANALYSIS_FIELDS = {"lightroom_adjustments", "develop_settings", "preset_path", "final_decision"}
ALLOWED_PROVIDERS = {"module", "model"}
ALLOWED_QUALITY = {"APPROVED", "RETRY_REQUIRED", "SOURCE_LIMITED", "TECHNICAL_FAILED", "FINAL_FAILED"}
TERMINAL = {"APPROVED", "SOURCE_LIMITED", "TECHNICAL_FAILED", "FINAL_FAILED"}
LEGAL_TRANSITIONS = {
    ("CREATED", "ANALYZING"),
    ("ANALYZING", "ADJUSTMENT_READY"), ("ANALYZING", "TECHNICAL_FAILED"),
    ("ADJUSTMENT_READY", "LIGHTROOM_PROCESSING"), ("ADJUSTMENT_READY", "TECHNICAL_FAILED"),
    ("LIGHTROOM_PROCESSING", "EXPORTED"), ("LIGHTROOM_PROCESSING", "TECHNICAL_FAILED"),
    ("EXPORTED", "EVALUATING"), ("EXPORTED", "TECHNICAL_FAILED"),
    ("EVALUATING", "APPROVED"), ("EVALUATING", "RETRY_REQUIRED"),
    ("EVALUATING", "SOURCE_LIMITED"), ("EVALUATING", "TECHNICAL_FAILED"),
    ("EVALUATING", "FINAL_FAILED"),
    ("RETRY_REQUIRED", "ADJUSTMENT_READY"), ("RETRY_REQUIRED", "FINAL_FAILED"),
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssertionError(f"Invalid JSON {path}: {exc}") from exc


def validate_analysis(data: dict, *, expect_invalid: bool = False) -> list[str]:
    failures: list[str] = []
    required = {
        "schema_version", "job_id", "attempt_id", "provider_type", "provider_version",
        "scene", "subjects", "technical_findings", "color_findings", "quality_risks",
        "confidence", "created_at",
    }
    missing = sorted(required - data.keys())
    if missing:
        failures.append(f"analysis missing fields: {missing}")
    if data.get("provider_type") not in ALLOWED_PROVIDERS:
        failures.append(f"invalid provider_type: {data.get('provider_type')}")
    forbidden = sorted(FORBIDDEN_ANALYSIS_FIELDS & data.keys())
    if expect_invalid:
        if not forbidden:
            failures.append("invalid model fixture did not contain a forbidden direct-adjustment field")
    elif forbidden:
        failures.append(f"analysis bypasses Adjustment Planner with fields: {forbidden}")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        failures.append("analysis confidence must be between 0 and 1")
    return failures


def validate_quality(data: dict) -> list[str]:
    failures: list[str] = []
    required = {
        "schema_version", "job_id", "attempt_id", "provider_type", "status", "scores",
        "reason_codes", "retry_recommendation", "source_limit_evidence", "created_at",
    }
    missing = sorted(required - data.keys())
    if missing:
        failures.append(f"quality missing fields: {missing}")
    status = data.get("status")
    if status not in ALLOWED_QUALITY:
        failures.append(f"invalid quality status: {status}")
    if status == "RETRY_REQUIRED":
        rec = data.get("retry_recommendation", {})
        if rec.get("recommended") is not True or not rec.get("strategy"):
            failures.append("RETRY_REQUIRED must include a recommended retry strategy")
    if status == "SOURCE_LIMITED" and not data.get("source_limit_evidence"):
        failures.append("SOURCE_LIMITED must include source_limit_evidence")
    if status == "TECHNICAL_FAILED" and data.get("scores"):
        failures.append("TECHNICAL_FAILED fixture must not pretend to be a quality-score failure")
    return failures


def validate_job_evidence(path: Path) -> list[str]:
    failures: list[str] = []
    data = load_json(path)
    required = {"job_id", "plan", "analysis_provider", "quality_provider", "state", "attempts"}
    missing = sorted(required - data.keys())
    if missing:
        return [f"job evidence missing fields: {missing}"]
    attempts = data.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        failures.append("job evidence attempts must be a non-empty list")
        return failures
    ids: set[str] = set()
    previous_no = -1
    for attempt in attempts:
        aid = attempt.get("attempt_id")
        ano = attempt.get("attempt_no")
        if not aid or aid in ids:
            failures.append("attempt_id values must be present and unique")
        ids.add(aid)
        if not isinstance(ano, int) or ano != previous_no + 1:
            failures.append("attempt_no values must be contiguous starting at 0")
        previous_no = ano if isinstance(ano, int) else previous_no
    max_retries = data.get("max_quality_retries")
    if isinstance(max_retries, int) and len(attempts) - 1 > max_retries:
        failures.append("job evidence exceeds max_quality_retries")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify T-021 dual-mode agent core and closed-loop contracts")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--job-evidence")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    failures: list[str] = []

    required_paths = [
        root / "skills" / "dual-mode-agent-core" / "SKILL.md",
        root / "skills" / "closed-loop-quality-reprocessing" / "SKILL.md",
        root / "harness" / "CONTRACT_T021_DUAL_MODE_CLOSED_LOOP.md",
        root / "harness" / "T021_DUAL_MODE_UPDATE_MANIFEST.json",
        root / "harness" / "schemas" / "t021_analysis_result.schema.json",
        root / "harness" / "schemas" / "t021_quality_result.schema.json",
        root / "harness" / "fixtures" / "t021_dual_mode" / "module_analysis_result.json",
        root / "harness" / "fixtures" / "t021_dual_mode" / "model_analysis_result.json",
        root / "harness" / "fixtures" / "t021_dual_mode" / "invalid_model_direct_adjustment.json",
        root / "harness" / "fixtures" / "t021_dual_mode" / "state_transition_cases.json",
        root / "skills" / "T021_SKILL_INVENTORY.json",
    ]
    for path in required_paths:
        if not path.exists():
            failures.append(f"Missing T-021 file: {path}")

    # T-019/T-020 preservation.
    regression_paths = [
        root / "skills" / "lightroom-apply-adapter" / "SKILL.md",
        root / "skills" / "lightroom-final-export-adapter" / "SKILL.md",
        root / "harness" / "CONTRACT_LIGHTROOM_APPLY_ADAPTER.md",
        root / "harness" / "CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md",
        root / "harness" / "scripts" / "verify_lightroom_apply_adapter_role.py",
        root / "harness" / "scripts" / "verify_lightroom_export_adapter.py",
    ]
    for path in regression_paths:
        if not path.exists():
            failures.append(f"T-019/T-020 preservation failure: missing {path}")

    skill_names = {p.parent.name for p in (root / "skills").glob("*/SKILL.md")}
    missing_baseline = sorted(BASELINE_SKILLS - skill_names)
    if missing_baseline:
        failures.append(f"Missing baseline skills: {missing_baseline}")
    missing_new = sorted(NEW_SKILLS - skill_names)
    if missing_new:
        failures.append(f"Missing T-021 skills: {missing_new}")
    if len(skill_names) < 27:
        failures.append(f"Expected at least 27 cumulative skills, found {len(skill_names)}")

    fixture_root = root / "harness" / "fixtures" / "t021_dual_mode"
    if fixture_root.exists():
        for name in ["module_analysis_result.json", "model_analysis_result.json"]:
            failures.extend(f"{name}: {msg}" for msg in validate_analysis(load_json(fixture_root / name)))
        invalid = load_json(fixture_root / "invalid_model_direct_adjustment.json")
        invalid_check = validate_analysis(invalid, expect_invalid=True)
        failures.extend(f"invalid_model_direct_adjustment.json: {msg}" for msg in invalid_check)
        forbidden = FORBIDDEN_ANALYSIS_FIELDS & invalid.keys()
        if not forbidden:
            failures.append("invalid model fixture is not testing a direct-adjustment bypass")

        for name in [
            "quality_approved.json", "quality_retry_required.json", "quality_source_limited.json",
            "technical_failed_export.json",
        ]:
            failures.extend(f"{name}: {msg}" for msg in validate_quality(load_json(fixture_root / name)))

        transitions = load_json(fixture_root / "state_transition_cases.json")
        legal_fixture = {tuple(x) for x in transitions.get("legal", [])}
        illegal_fixture = {tuple(x) for x in transitions.get("illegal", [])}
        for edge in legal_fixture:
            if edge not in LEGAL_TRANSITIONS:
                failures.append(f"Fixture marks non-contract transition legal: {edge}")
        for edge in illegal_fixture:
            if edge in LEGAL_TRANSITIONS:
                failures.append(f"Fixture marks contract transition illegal: {edge}")
        for src, dst in LEGAL_TRANSITIONS:
            if src in TERMINAL:
                failures.append(f"Terminal state has outgoing legal transition: {(src, dst)}")

        policies = load_json(fixture_root / "plan_policies.json").get("plans", {})
        expected = {
            "free": ("module", "module", 1, False),
            "lite": ("module", "module", 2, False),
            "standard": ("model", "model", 2, True),
            "pro": ("model", "model", 3, True),
            "t021_mvp": ("module", "module", 2, False),
        }
        for name, (ap, qp, retries, model) in expected.items():
            item = policies.get(name, {})
            actual = (item.get("analysis_provider"), item.get("quality_provider"), item.get("max_quality_retries"), item.get("allow_model_loading"))
            if actual != (ap, qp, retries, model):
                failures.append(f"Plan policy mismatch for {name}: {actual}")

        retry = load_json(fixture_root / "retry_sequence.json")
        attempts = retry.get("attempts", [])
        if len(attempts) - 1 > retry.get("max_quality_retries", -1):
            failures.append("Retry fixture exceeds retry budget")
        if len({a.get("attempt_id") for a in attempts}) != len(attempts):
            failures.append("Retry fixture reuses attempt_id")
        if len({a.get("plan_delta_hash") for a in attempts}) != len(attempts):
            failures.append("Retry fixture repeats plan_delta_hash")

    inventory_path = root / "skills" / "T021_SKILL_INVENTORY.json"
    if inventory_path.exists():
        inv = load_json(inventory_path)
        if inv.get("baseline_skill_count") != 25 or inv.get("skill_count") != 27:
            failures.append("T021 skill inventory counts are incorrect")
        expected_t021_skills = BASELINE_SKILLS | NEW_SKILLS
        if set(inv.get("skills", [])) != expected_t021_skills:
            failures.append("T021 skill inventory does not match the T-021 snapshot")
        if not expected_t021_skills.issubset(skill_names):
            failures.append("Current skill directories do not preserve the complete T-021 snapshot")

    if args.job_evidence:
        evidence_path = Path(args.job_evidence).resolve()
        if not evidence_path.exists():
            failures.append(f"Job evidence does not exist: {evidence_path}")
        else:
            failures.extend(validate_job_evidence(evidence_path))
    elif args.strict:
        failures.append("--job-evidence is required in --strict mode")

    if failures:
        print("FAIL: T-021 verification failed")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PASS: T-021 provider, state, retry, failure separation, skill preservation, and T-019/T-020 regression contracts passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
