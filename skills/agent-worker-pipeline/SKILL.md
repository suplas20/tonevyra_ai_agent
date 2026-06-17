# Agent Worker Pipeline Skill

## Purpose
Connect all implemented modules into one bounded one-photo processing pipeline.

The worker is the execution spine of the MVP. It must not hide stage decisions only in logs; every durable transition needs DB and artifact evidence.

## Required Flow
metadata -> preview -> vision -> correction_plan -> lightroom -> export -> quality -> final status

## Stage Commit Order
```text
artifact temp write → flush/fsync → atomic rename → checksum/size
→ DB transaction → task_artifacts/stage_results → image_tasks status
→ task_events with loop evidence → commit
```

## Rules
- Worker concurrency is 1 in MVP.
- Persist artifacts before marking stages complete.
- Use mock vision and fake Lightroom until real integration tickets are approved.
- Record stage_results and task_events.
- Add `processing_loop` evidence for autonomous stage movement.
- Preserve sticky `requires_review` from correction plan to quality gate.
- Never call real model or Lightroom directly from a stage that is configured for mock/fake backend.
- Recovery must be able to resume from the last durable stage.

## Final Status
`PASS`, `REVIEW_REQUIRED`, or `FAILED`.

`SKIPPED` is allowed only for watcher/unsupported file decisions.

## Harness Validation
- `harness/scripts/run_worker_pipeline_test.py`
- `harness/scripts/run_smoke_pipeline.py`
- `harness/scripts/verify_loop_events.py`
