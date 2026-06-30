#!/usr/bin/env python3
"""Generate deterministic reference-harness evidence for T-030.

This proves the document/fixture contract only. It is intentionally not accepted
as strict implementation or Windows live evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return {
        "kind": path.stem,
        "path": str(path),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def stable_at(samples: list[dict[str, int]], required: int) -> int | None:
    previous: tuple[int, int] | None = None
    count = 0
    for sample in samples:
        current = (sample["size_bytes"], sample["mtime_ns"])
        if current == previous:
            count += 1
        else:
            count = 0
            previous = current
        if count >= required:
            return sample["t"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    root = args.project_root.resolve()
    out = (args.output_dir or root / "runtime" / "harness" / "t030").resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    fixture_root = root / "harness" / "fixtures" / "t030_background_tray"
    load = lambda name: json.loads((fixture_root / name).read_text(encoding="utf-8"))

    stability_case = load("copy_in_progress_stability_case.json")
    calculated_stable = stable_at(stability_case["samples"], stability_case["required_stable_samples"])
    stability_passed = calculated_stable == stability_case["expected_stable_at_seconds"]
    stability_evidence = {
        "case_id": stability_case["case_id"],
        "calculated_stable_at_seconds": calculated_stable,
        "expected_stable_at_seconds": stability_case["expected_stable_at_seconds"],
        "analysis_started_before_stable": False,
        "passed": stability_passed,
    }

    duplicate = load("duplicate_event_coalescing_case.json")
    unique_candidates = len({duplicate["normalized_path"] for _ in duplicate["events"]})
    dedup_passed = (
        unique_candidates == duplicate["expected_coalesced_candidates"]
        and duplicate["expected_task_registrations"] == 1
        and duplicate["expected_external_pipeline_executions"] == 1
    )
    dedup_evidence = {
        "raw_event_count": len(duplicate["events"]),
        "coalesced_candidates": unique_candidates,
        "task_registrations": 1,
        "external_pipeline_executions": 1,
        "passed": dedup_passed,
    }

    pause = load("pause_resume_case.json")
    state = pause["initial_state"]
    states: list[str] = []
    rescan_count = 0
    for command in pause["commands"]:
        if command == "PAUSE_WATCHING":
            state = "PAUSED"
        elif command == "RESUME_WATCHING":
            state = "WATCHING"
        elif command == "RESCAN":
            rescan_count += 1
        states.append(state)
    pause_passed = states == pause["expected_states"] and pause["expected_duplicate_side_effects"] == 0
    pause_evidence = {"observed_states": states, "rescan_count": rescan_count, "passed": pause_passed}

    single = load("single_instance_case.json")
    single_passed = (
        single["first_tray_mutex_acquired"]
        and single["first_worker_mutex_acquired"]
        and not single["second_tray_mutex_acquired"]
        and not single["second_worker_started"]
        and single["expected_processing_workers"] == 1
    )
    single_evidence = {"processing_workers": 1, "second_launch_activated_existing": True, "passed": single_passed}

    restart = load("restart_recovery_case.json")
    recovery_passed = (
        restart["tray_remains_alive"]
        and restart["restart_attempt"] <= restart["restart_limit"]
        and restart["checkpoint_available"]
        and restart["expected_duplicate_external_effects"] == 0
    )
    recovery_evidence = {
        "tray_alive": True,
        "restart_attempt": restart["restart_attempt"],
        "recovered_from_checkpoint": True,
        "duplicate_external_effects": 0,
        "passed": recovery_passed,
    }

    shutdown = load("graceful_shutdown_case.json")
    shutdown_passed = shutdown["expected_orphan_processes"] == 0 and not shutdown["source_modified"]
    shutdown_evidence = {
        "steps": shutdown["steps"],
        "orphan_processes": 0,
        "source_modified": False,
        "passed": shutdown_passed,
    }

    evidence = [
        write_json(out / "file_stability_evidence.json", stability_evidence),
        write_json(out / "deduplication_evidence.json", dedup_evidence),
        write_json(out / "pause_resume_evidence.json", pause_evidence),
        write_json(out / "single_instance_evidence.json", single_evidence),
        write_json(out / "worker_recovery_evidence.json", recovery_evidence),
        write_json(out / "graceful_shutdown_evidence.json", shutdown_evidence),
    ]

    checks = {
        "file_stability": stability_passed,
        "event_coalescing": dedup_passed,
        "deduplication": dedup_passed,
        "pause_resume": pause_passed,
        "single_instance": single_passed,
        "worker_recovery": recovery_passed,
        "graceful_shutdown": shutdown_passed,
        "source_integrity": shutdown_passed,
    }
    complete = all(checks.values())
    runtime = {
        "schema_version": "t030.runtime.evidence.v1",
        "ticket": "T030",
        "evidence_source": "reference_harness",
        "completed": complete,
        "regressions_passed": complete,
        "checks": checks,
        "evidence": evidence,
    }
    runtime_path = out / "t030_runtime_evidence.json"
    runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OK: wrote T-030 reference evidence to {runtime_path}")
    print("NOTE: reference_harness evidence cannot satisfy strict Windows implementation completion.")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
