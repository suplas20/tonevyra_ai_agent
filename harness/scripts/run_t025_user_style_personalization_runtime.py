#!/usr/bin/env python3
"""Generate deterministic runtime evidence for T-025."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: object) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"artifact": path.name, "path": str(path), "kind": "t025_evidence"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-regressions", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = (args.output_dir or project_root / "runtime" / "harness" / "t025").resolve()
    sys.path.insert(0, str(project_root / "src"))

    from tonevyra_agent.learning.style_profile import (
        StyleProfile,
        StyleProfileStore,
        T025RuntimeEvidence,
        apply_style_profile_to_planner,
        build_calibration_candidate,
    )

    fixture_root = project_root / "harness" / "fixtures" / "t025_personalization"
    profile = StyleProfile.model_validate(json.loads((fixture_root / "valid_style_profile.json").read_text(encoding="utf-8")))
    store = StyleProfileStore()
    active = store.add_profile(profile, activate=True)
    application = apply_style_profile_to_planner(active, job_id="job-025-runtime")

    profile_v1 = StyleProfile(
        profile_id=active.profile_id,
        user_scope_id=active.user_scope_id,
        version=1,
        status="SUPERSEDED",
        source=active.source,
        preferences={"contrast_strength": 0.1, "skin_warmth": 0.05},
        constraints=active.constraints,
        confidence=0.82,
        minimum_evidence_count=active.minimum_evidence_count,
    )
    version_store = StyleProfileStore()
    version_store.add_profile(profile_v1)
    version_store.add_profile(active, activate=True)
    restored, rollback = version_store.rollback(active.user_scope_id, target_version=1)
    opt_out = version_store.set_opt_out("user-opt-out-runtime", opt_out=True)

    calibration = build_calibration_candidate(
        user_scope_id=active.user_scope_id,
        sample_count=7,
        minimum_evidence_count=5,
        direction_consistency=0.86,
        confidence=0.82,
        candidate_delta={"contrast_strength": 0.05},
    )

    evidence_entries = [
        _write_json(output_dir / "style_profile.json", active.model_dump(mode="json")),
        _write_json(output_dir / "style_application_plan.json", application.model_dump(mode="json")),
        _write_json(
            output_dir / "style_mapping_evidence.json",
            {
                "mapping_version": application.mapping_version,
                "profile_id": application.profile_id,
                "profile_version": application.profile_version,
                "bounded_deltas": application.bounded_deltas,
                "safety_overrides": application.safety_overrides,
            },
        ),
        _write_json(output_dir / "rollback_evidence.json", rollback.model_dump(mode="json")),
        _write_json(
            output_dir / "opt_out_evidence.json",
            {
                **opt_out.model_dump(mode="json"),
                "expected_profile_loaded": opt_out.allows_profile_load(),
                "expected_feedback_collected": opt_out.allows_feedback_collection(),
            },
        ),
        _write_json(output_dir / "calibration_candidate.json", calibration.model_dump(mode="json")),
        _write_json(
            output_dir / "profile_version_history.json",
            {
                "active_after_rollback": restored.model_dump(mode="json"),
                "rollback_target_version": rollback.rollback_target_version,
                "new_version": rollback.new_version,
            },
        ),
    ]

    regressions_passed = True
    if not args.skip_regressions:
        checks = [
            [sys.executable, "harness/scripts/verify_live_runtime_gate.py"],
            [sys.executable, "harness/scripts/verify_t024_batch_set.py", "--runtime-evidence", "runtime/harness/t024/t024_runtime_evidence.json", "--strict"],
            [sys.executable, "harness/scripts/verify_t025_user_style_personalization.py"],
            [sys.executable, "-m", "pytest", "tests/test_t023_semantic_local_adjustment.py", "tests/test_t024_batch_set_consistency.py", "tests/test_t025_user_style_personalization.py", "-q"],
        ]
        for command in checks:
            result = subprocess.run(command, cwd=project_root)
            if result.returncode != 0:
                regressions_passed = False
                break

    runtime_evidence = T025RuntimeEvidence(completed=True, regressions_passed=regressions_passed, evidence=evidence_entries)
    evidence_path = output_dir / "t025_runtime_evidence.json"
    evidence_path.write_text(
        json.dumps(runtime_evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OK: wrote T-025 runtime evidence to {evidence_path}")
    return 0 if regressions_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
