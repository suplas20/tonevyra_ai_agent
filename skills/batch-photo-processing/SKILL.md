# Batch Photo Processing Skill

## Purpose

Use this skill for T-024 batch submission, chunked execution, per-item isolation, partial failure, progress persistence, and safe resume.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t024/T-024_Batch_Processing_Photo_Set_Consistency_Work_Order.md
3. skills/batch-photo-processing/SKILL.md
4. skills/photo-set-consistency/SKILL.md
5. skills/agent-worker-pipeline/SKILL.md
6. skills/recovery-error-handling/SKILL.md
7. skills/testing-harness/SKILL.md
```

## Identifier Rule

```text
batch_id != set_id != job_id != attempt_id
```

Every photo remains an independent job with its own attempts, artifacts, quality decision, and retry budget.

## Default Execution Policy

- default chunk size: 10 photos;
- preserve current single-worker/concurrency policy unless explicitly changed;
- bounded queue and bounded retries;
- completed items are not re-executed on resume;
- one item failure does not automatically terminate all remaining items.

## Partial Failure

Batch summary may be `COMPLETED`, `PARTIAL_FAILED`, or `FAILED`, but must preserve each item result. Never replace item-level failure details with only a batch-level status.

## Idempotency

Use stable submission and item idempotency keys. Duplicate batch submission must not duplicate job creation, Lightroom apply, export, or usage accounting.

## Evidence

Persist batch manifest, chunk plan, item progress, checkpoints, failure isolation, resume decision, and final summary.

## Acceptance Checklist

- default 10-photo chunk is enforced;
- IDs are isolated;
- item retries do not affect another item;
- partial failure continues safely;
- resume skips completed items;
- duplicate submission is idempotent.
