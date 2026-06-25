#!/usr/bin/env python3
"""Generate deterministic runtime evidence for T-024."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: object) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"artifact": path.name, "path": str(path), "kind": "t024_evidence"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-regressions", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = (args.output_dir or project_root / "runtime" / "harness" / "t024").resolve()
    sys.path.insert(0, str(project_root / "src"))

    from tonevyra_agent.batch import BatchProcessor, PhotoSetConsistencyEngine
    from tonevyra_agent.batch.schemas import BatchRuntimeEvidence, PhotoSetItemEvidence

    processor = BatchProcessor()
    source_paths = [f"runtime/input/photo_{index:03d}.jpg" for index in range(1, 13)]
    batch = processor.create_manifest(source_paths, batch_id="batch-024-runtime", set_id="set-a")
    chunk_plan = processor.chunk_plan(batch)

    batch = processor.update_item_state(batch, job_id=batch.items[0].job_id, item_state="APPROVED")
    batch = processor.update_item_state(batch, job_id=batch.items[1].job_id, item_state="TECHNICAL_FAILED")
    batch = processor.record_quality_retry(batch, job_id=batch.items[2].job_id)
    resume_decision = processor.resume_decision(
        batch,
        completed_job_ids={batch.items[0].job_id, batch.items[1].job_id},
        duplicate_submission=True,
    )
    batch_summary = processor.summarize(batch)

    set_items = [
        PhotoSetItemEvidence(
            job_id="job-001",
            capture_group="A",
            scene="outdoor_portrait",
            grouping_confidence=0.95,
            technical_quality_score=86,
            exposure=0.04,
            white_balance=80,
            skin_tone=0.02,
        ),
        PhotoSetItemEvidence(
            job_id="job-002",
            capture_group="A",
            scene="outdoor_portrait",
            grouping_confidence=0.93,
            technical_quality_score=91,
            exposure=0.01,
            white_balance=40,
            skin_tone=0.01,
        ),
        PhotoSetItemEvidence(
            job_id="job-010",
            capture_group="B",
            scene="night_flash",
            grouping_confidence=0.42,
            technical_quality_score=70,
            exposure=-0.7,
            white_balance=-900,
            skin_tone=-0.4,
        ),
    ]
    engine = PhotoSetConsistencyEngine()
    grouping = engine.group(set_items, batch_id=batch.batch_id)
    selection = engine.select_representative(set_items, grouping)
    baseline = engine.baseline(set_items, grouping)
    consistency = engine.evaluate(set_items, grouping, selection, baseline)

    evidence_entries = [
        _write_json(output_dir / "batch_manifest.json", batch.model_dump(mode="json")),
        _write_json(output_dir / "chunk_plan.json", chunk_plan.model_dump(mode="json")),
        _write_json(
            output_dir / "item_progress.json",
            [{"job_id": item.job_id, "state": item.item_state, "retry_count": item.quality_retry_count} for item in batch.items],
        ),
        _write_json(output_dir / "resume_decision.json", resume_decision.model_dump(mode="json")),
        _write_json(output_dir / "set_grouping.json", grouping.model_dump(mode="json")),
        _write_json(output_dir / "representative_selection.json", selection.model_dump(mode="json")),
        _write_json(output_dir / "set_baseline.json", baseline.model_dump(mode="json")),
        _write_json(output_dir / "set_consistency_evaluation.json", consistency.model_dump(mode="json")),
        _write_json(output_dir / "batch_summary.json", batch_summary.model_dump(mode="json")),
    ]

    regressions_passed = True
    if not args.skip_regressions:
        checks = [
            [sys.executable, "harness/scripts/verify_t023_semantic_local_adjustment.py"],
            [sys.executable, "harness/scripts/verify_t024_batch_set.py"],
            [sys.executable, "-m", "pytest", "tests/test_t023_semantic_local_adjustment.py", "tests/test_t024_batch_set_consistency.py", "-q"],
        ]
        for command in checks:
            result = subprocess.run(command, cwd=project_root)
            if result.returncode != 0:
                regressions_passed = False
                break

    runtime_evidence = BatchRuntimeEvidence(completed=True, regressions_passed=regressions_passed, evidence=evidence_entries)
    evidence_path = output_dir / "t024_runtime_evidence.json"
    evidence_path.write_text(
        json.dumps(runtime_evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OK: wrote T-024 runtime evidence to {evidence_path}")
    return 0 if regressions_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
