"""Deterministic T-024 batch processing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from tonevyra_agent.batch.schemas import (
    DEFAULT_CHUNK_SIZE,
    MAX_MVP_CHUNK_SIZE,
    BatchItem,
    BatchJob,
    BatchSummary,
    ChunkPlan,
    ResumeDecision,
    TERMINAL_ITEM_STATES,
    utc_now,
)


class BatchProcessor:
    """Small orchestration layer above the one-photo worker contract."""

    def __init__(self, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        if chunk_size < 1 or chunk_size > MAX_MVP_CHUNK_SIZE:
            raise ValueError(f"T-024 MVP chunk_size must be between 1 and {MAX_MVP_CHUNK_SIZE}")
        self.chunk_size = chunk_size

    def create_manifest(
        self,
        source_paths: Iterable[str | Path],
        *,
        batch_id: str,
        set_id: str | None = None,
    ) -> BatchJob:
        """Create a stable manifest; duplicate submissions derive the same item keys."""

        normalized_paths = [str(Path(path)) for path in source_paths]
        items: list[BatchItem] = []
        for index, source_path in enumerate(normalized_paths, start=1):
            job_id = _stable_job_id(batch_id, source_path, index)
            items.append(
                BatchItem(
                    job_id=job_id,
                    source_path=source_path,
                    item_state="QUEUED",
                    idempotency_key=f"{batch_id}:{_stable_hash(source_path)[:12]}",
                    set_id=set_id,
                    attempt_id=f"{job_id}:attempt-000",
                    attempt_no=0,
                )
            )
        return BatchJob(batch_id=batch_id, chunk_size=self.chunk_size, items=items, state="CREATED")

    def chunk_plan(self, batch: BatchJob) -> ChunkPlan:
        chunks = [
            [item.job_id for item in batch.items[index : index + batch.chunk_size]]
            for index in range(0, len(batch.items), batch.chunk_size)
        ]
        return ChunkPlan(batch_id=batch.batch_id, chunk_size=batch.chunk_size, chunks=chunks)

    def resume_decision(
        self,
        batch: BatchJob,
        *,
        completed_job_ids: set[str] | None = None,
        duplicate_submission: bool = False,
    ) -> ResumeDecision:
        completed = set(completed_job_ids or set())
        for item in batch.items:
            if item.item_state in TERMINAL_ITEM_STATES:
                completed.add(item.job_id)
        reexecute = [item.job_id for item in batch.items if item.job_id not in completed]
        skipped = [item.job_id for item in batch.items if item.job_id in completed]
        return ResumeDecision(
            batch_id=batch.batch_id,
            reexecute_job_ids=reexecute,
            skipped_completed_job_ids=skipped,
            duplicate_submission=duplicate_submission,
        )

    def update_item_state(
        self,
        batch: BatchJob,
        *,
        job_id: str,
        item_state: str,
        quality_retry_count: int | None = None,
    ) -> BatchJob:
        items = []
        found = False
        for item in batch.items:
            if item.job_id != job_id:
                items.append(item)
                continue
            found = True
            data = item.model_dump()
            data["item_state"] = item_state
            if quality_retry_count is not None:
                data["quality_retry_count"] = quality_retry_count
            items.append(BatchItem.model_validate(data))
        if not found:
            raise ValueError(f"unknown batch job_id: {job_id}")
        return BatchJob(
            batch_id=batch.batch_id,
            chunk_size=batch.chunk_size,
            items=items,
            state=self.summarize(BatchJob(batch_id=batch.batch_id, chunk_size=batch.chunk_size, items=items)).state,
            created_at=batch.created_at,
            updated_at=utc_now(),
        )

    def record_quality_retry(self, batch: BatchJob, *, job_id: str) -> BatchJob:
        """Increment only the selected item's retry count."""

        items = []
        found = False
        for item in batch.items:
            if item.job_id != job_id:
                items.append(item)
                continue
            found = True
            if item.quality_retry_count >= item.max_quality_retries:
                raise ValueError(f"quality retry budget exhausted for {job_id}")
            data = item.model_dump()
            data["quality_retry_count"] = item.quality_retry_count + 1
            data["attempt_no"] = item.attempt_no + 1
            data["attempt_id"] = f"{item.job_id}:attempt-{data['attempt_no']:03d}"
            items.append(BatchItem.model_validate(data))
        if not found:
            raise ValueError(f"unknown batch job_id: {job_id}")
        return BatchJob(
            batch_id=batch.batch_id,
            chunk_size=batch.chunk_size,
            items=items,
            state=batch.state,
            created_at=batch.created_at,
            updated_at=utc_now(),
        )

    def summarize(self, batch: BatchJob) -> BatchSummary:
        completed_items = sum(1 for item in batch.items if item.item_state in TERMINAL_ITEM_STATES)
        failed_items = sum(1 for item in batch.items if item.is_failed)
        total = len(batch.items)
        if total == 0:
            state = "FAILED"
        elif failed_items == total:
            state = "FAILED"
        elif failed_items > 0:
            state = "PARTIAL_FAILED"
        elif completed_items == total:
            state = "COMPLETED"
        else:
            state = "PROCESSING"
        return BatchSummary(
            batch_id=batch.batch_id,
            state=state,
            total_items=total,
            completed_items=completed_items,
            failed_items=failed_items,
            item_results=[
                {
                    "job_id": item.job_id,
                    "item_state": item.item_state,
                    "quality_retry_count": item.quality_retry_count,
                    "set_id": item.set_id,
                }
                for item in batch.items
            ],
            continue_remaining=state in {"PROCESSING", "PARTIAL_FAILED"},
        )


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_job_id(batch_id: str, source_path: str, index: int) -> str:
    return f"job-{index:03d}-{_stable_hash(batch_id + ':' + source_path)[:8]}"
