from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.batch import BatchProcessor, PhotoSetConsistencyEngine
from tonevyra_agent.batch.schemas import BatchJob, PhotoSetItemEvidence, SetConsistencyResult


def test_batch_manifest_fixture_matches_contract() -> None:
    payload = json.loads(Path("harness/fixtures/t024_batch_set/valid_batch_manifest.json").read_text(encoding="utf-8"))
    batch = BatchJob.model_validate(payload)

    assert batch.schema_version == "t024.batch.job.v1"
    assert batch.chunk_size == 10
    assert len({item.job_id for item in batch.items}) == 10
    assert len({item.idempotency_key for item in batch.items}) == 10


def test_batch_chunk_size_is_bounded_to_mvp_default() -> None:
    processor = BatchProcessor()
    batch = processor.create_manifest([f"runtime/input/photo_{index:03d}.jpg" for index in range(12)], batch_id="batch-024")
    chunk_plan = processor.chunk_plan(batch)

    assert batch.chunk_size == 10
    assert [len(chunk) for chunk in chunk_plan.chunks] == [10, 2]
    with pytest.raises(ValueError):
        BatchProcessor(chunk_size=11)


def test_duplicate_submission_resume_skips_completed_items() -> None:
    fixture = json.loads(Path("harness/fixtures/t024_batch_set/resume_idempotency_case.json").read_text(encoding="utf-8"))
    processor = BatchProcessor()
    batch = processor.create_manifest(
        [f"runtime/input/{job_id}.jpg" for job_id in fixture["completed_job_ids"] + fixture["pending_job_ids"]],
        batch_id="batch-resume",
    )
    by_index = {index: item.job_id for index, item in enumerate(batch.items)}
    completed = {by_index[0], by_index[1]}
    decision = processor.resume_decision(batch, completed_job_ids=completed, duplicate_submission=True)

    assert decision.duplicate_submission is True
    assert decision.skipped_completed_job_ids == [by_index[0], by_index[1]]
    assert decision.reexecute_job_ids == [by_index[2]]


def test_retry_isolation_does_not_touch_other_items() -> None:
    fixture = json.loads(Path("harness/fixtures/t024_batch_set/retry_isolation_case.json").read_text(encoding="utf-8"))
    processor = BatchProcessor()
    batch = processor.create_manifest(["runtime/input/a.jpg", "runtime/input/b.jpg"], batch_id="batch-retry")
    job_a = batch.items[0].job_id
    job_b = batch.items[1].job_id

    retried = processor.record_quality_retry(batch, job_id=job_a)
    counts = {item.job_id: item.quality_retry_count for item in retried.items}

    assert counts[job_a] == fixture["job_a"]["quality_retry_count"]
    assert counts[job_b] == fixture["expected_job_b_count_after_job_a_retry"]


def test_partial_failure_preserves_item_results_and_continues() -> None:
    fixture = json.loads(Path("harness/fixtures/t024_batch_set/partial_failure_case.json").read_text(encoding="utf-8"))
    processor = BatchProcessor()
    batch = processor.create_manifest(["a.jpg", "b.jpg", "c.jpg"], batch_id="batch-partial")
    for item, result in zip(batch.items, fixture["items"], strict=True):
        batch = processor.update_item_state(batch, job_id=item.job_id, item_state=result["status"])

    summary = processor.summarize(batch)

    assert summary.state == fixture["expected_batch_status"]
    assert summary.continue_remaining is fixture["continue_remaining"]
    assert len(summary.item_results) == 3
    assert summary.failed_items == 1


def test_photo_set_grouping_representative_baseline_and_outlier_protection() -> None:
    cases = json.loads(Path("harness/fixtures/t024_batch_set/grouping_cases.json").read_text(encoding="utf-8"))["cases"]
    items = [
        PhotoSetItemEvidence(
            job_id=case["job_id"],
            capture_group=case["capture_group"],
            scene=case["scene"],
            grouping_confidence=case["grouping_confidence"],
            technical_quality_score=90.0 if case["job_id"] == "job-002" else 82.0,
            exposure=0.02 if case["job_id"] == "job-002" else 0.08,
            white_balance=60 if case["job_id"] == "job-002" else 100,
        )
        for case in cases
    ]

    engine = PhotoSetConsistencyEngine()
    grouping = engine.group(items, batch_id="batch-024-001")
    selection = engine.select_representative(items, grouping)
    baseline = engine.baseline(items, grouping)
    result = engine.evaluate(items, grouping, selection, baseline)

    assert grouping.grouped_job_ids == ["job-001", "job-002"]
    assert grouping.outlier_job_ids == ["job-010"]
    assert selection.representative_job_id == "job-002"
    assert baseline.baseline_method == "bounded_relative_median"
    assert any(item.job_id == "job-010" and item.outlier for item in result.item_results)
    assert result.overall_score >= 85


def test_set_consistency_fixture_matches_contract() -> None:
    payload = json.loads(
        Path("harness/fixtures/t024_batch_set/valid_set_consistency_result.json").read_text(encoding="utf-8")
    )
    result = SetConsistencyResult.model_validate(payload)

    assert result.schema_version == "t024.set.consistency.v1"
    assert result.representative_job_id == "job-005"
    assert result.item_results[1].outlier is True


def test_batch_id_set_id_job_id_attempt_id_must_be_distinct() -> None:
    with pytest.raises(ValidationError):
        BatchJob(
            batch_id="batch-1",
            items=[
                {
                    "job_id": "job-1",
                    "source_path": "a.jpg",
                    "item_state": "QUEUED",
                    "idempotency_key": "batch-1:a",
                    "set_id": "job-1",
                    "attempt_id": "attempt-1",
                }
            ],
        )
