# Recovery Loop Skill

## Purpose
Recover unfinished tasks after crash, shutdown, timeout, or interrupted runs using durable evidence.

This is the loop-specific companion to `recovery-error-handling`.

## Source of Truth
PostgreSQL task state, task_artifacts records, artifact file existence, checksum verification, stage_results, task_events, Lightroom bridge request/response files, and exported output existence.

Logs are debug-only and must not be used as the primary recovery source.

## Required Loop Name
`recovery_loop`

## Required Artifact
`recovery_decision.json`

## Rules
- Never guess that a stage completed successfully.
- Resume only from a safe stage.
- Fail safely when evidence is inconsistent.
- Do not resume terminal tasks automatically.
- Do not invent new statuses, stages, or error codes.
- Record `RECOVERY_RESUMED`, safe failure, or no-op as task event evidence.
- Recovery must run before accepting new tasks.

## Validation
`harness/scripts/run_recovery_test.py`
