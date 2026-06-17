# Prompt — Implement Recovery Harness

Read `AGENTS.md`, `skills/recovery-error-handling/SKILL.md`, `skills/agent-worker-pipeline/SKILL.md`, and `harness/CONTRACT.md`.

Implement recovery behavior so `harness/scripts/run_recovery_test.py` can validate restart scenarios.

Required scenarios:

1. `status=ANALYZING` and `vision_structured.json` exists → resume from correction planning.
2. `status=LIGHTROOM_REQUESTED` and Lightroom response exists → process response.
3. `status=EXPORT_DONE` and export exists → resume from quality check.
4. final status `PASS` but export missing → mark `FAILED` or schedule re-export with structured error.

Do not use logs as the recovery source.
Use PostgreSQL state + artifact records + file existence.
