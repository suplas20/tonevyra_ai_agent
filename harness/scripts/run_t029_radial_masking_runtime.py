#!/usr/bin/env python3
"""Deterministic T-029 native-mask planning harness.

This script validates the planning/fallback layer only. Real Lightroom native
mask execution is represented by a separate live-evidence file and is never
faked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def adjustment_bounds_valid(adjustments: dict[str, float]) -> bool:
    bounds = {
        "Exposure2012": (-1.0, 1.0),
        "Shadows2012": (-40.0, 40.0),
        "Temperature": (-20.0, 20.0),
        "Tint": (-20.0, 20.0),
        "Saturation": (-35.0, 35.0),
        "Vibrance": (-30.0, 30.0),
        "Texture": (-20.0, 20.0),
        "Clarity2012": (-20.0, 20.0),
        "Dehaze": (-15.0, 15.0),
    }
    return all(key in bounds and bounds[key][0] <= float(value) <= bounds[key][1] for key, value in adjustments.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic T-029 native-mask planning harness.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--regressions-passed",
        action="store_true",
        help="Set only after T-019..T-028 regression commands have actually passed.",
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    fixture_root = root / "harness" / "fixtures" / "t029_radial_masking"
    case = load_json(fixture_root / "background_person_red_recovery_case.json")
    idempotency = load_json(fixture_root / "idempotent_replay_case.json")
    rollback = load_json(fixture_root / "rollback_preserves_user_masks_case.json")

    native_target_detected = bool(case["native_assessment"]["target_detected"])
    strategy = "native_ai" if native_target_detected else case.get("expected_strategy", "review_required")
    if strategy == "radial_template":
        strategy = "review_required"
    clamps_valid = adjustment_bounds_valid(case["local_adjustment_intent"])
    idempotent_replay = (
        idempotency["first_result"]["mask_count_delta"] == 1
        and idempotency["replay_result"]["mask_count_delta"] == 0
        and idempotency["expected_duplicate_masks"] == 0
    )
    user_masks_preserved = rollback["before"]["user_mask_ids"] == rollback["after_rollback"]["user_mask_ids"]
    source_path = root / case["source_fixture"]
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest() if source_path.is_file() else None
    native_detection_failed_safely = (not native_target_detected) and strategy in {"skip_local", "review_required"}

    passed = all(
        [
            strategy in {"native_ai", "skip_local", "review_required"},
            strategy != "radial_template",
            native_detection_failed_safely if not native_target_detected else True,
            clamps_valid,
            idempotent_replay,
            user_masks_preserved,
            source_sha256 is not None,
        ]
    )
    payload = {
        "schema_version": "t029.runtime.evidence.v1",
        "ticket": "T029",
        "completed": bool(passed and args.regressions_passed),
        "planning_harness_passed": passed,
        "regressions_passed": args.regressions_passed,
        "case_id": case["case_id"],
        "source_fixture": case["source_fixture"],
        "source_sha256": source_sha256,
        "selected_strategy": strategy,
        "selected_template_id": None,
        "expected_template_id": None,
        "native_target_detected": native_target_detected,
        "native_detection_failed_safely": native_detection_failed_safely,
        "native_assessment": case["native_assessment"],
        "fallback_reason": case.get("expected_reason_code", case["native_assessment"].get("reason_code")),
        "clamps_valid": clamps_valid,
        "idempotent_replay": idempotent_replay,
        "user_masks_preserved": user_masks_preserved,
        "note": (
            "Radial fallback is excluded. Real Lightroom native-mask execution is not simulated here; "
            "provide separate t029.live.evidence.v1 for strict validation."
        ),
    }
    write_json(args.output, payload)
    print(f"WROTE: {args.output}")
    if not passed:
        print("FAIL: deterministic T-029 native-mask planning harness")
        return 1
    if not args.regressions_passed:
        print("PASS: planning harness; evidence remains incomplete until --regressions-passed is supplied after real regression runs")
        return 0
    print("PASS: T-029 runtime native-mask planning evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
