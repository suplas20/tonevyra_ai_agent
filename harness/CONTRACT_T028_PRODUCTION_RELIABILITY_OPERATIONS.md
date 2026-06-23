# T-028 Production Reliability and Agent Operations Harness Contract

## Contract

- Durable checkpoints advance only after verified operation evidence.
- Analysis, planning, apply, export, artifact, quality, and usage boundaries are idempotent.
- Leases have heartbeat/expiry and stale recovery.
- Crash restart resumes from the last safe checkpoint.
- Partial DB/file commits are reconciled without silent data overwrite.
- Retries and waits are bounded; manual intervention is explicit.
- Structured logs, metrics, health, and audited operator actions are required.
- Strict evidence includes fault injection and soak results with no duplicate external effects.
- T-019 through T-027 regressions remain mandatory.
