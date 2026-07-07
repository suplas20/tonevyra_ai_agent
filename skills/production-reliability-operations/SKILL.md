# Production Reliability and Agent Operations Skill

## Purpose

Use this skill for T-028 health, structured logging, metrics, fault classification, operator CLI, reconciliation, and release-readiness soak testing.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t028/T-028_Production_Reliability_Agent_Operations_Work_Order.md
3. skills/production-reliability-operations/SKILL.md
4. skills/resumable-idempotent-jobs/SKILL.md
5. skills/recovery-error-handling/SKILL.md
6. skills/recovery-loop/SKILL.md
7. skills/cli-operations/SKILL.md
8. skills/testing-harness/SKILL.md
```

## Fault Classes

```text
TRANSIENT
RECOVERABLE_RESTART
MANUAL_INTERVENTION
TERMINAL
```

Every technical failure needs a class, error code, bounded recovery policy, and evidence.

## Observability

Structured logs and metrics must include correlation/job/attempt/stage/component/provider/plan/error/duration/retry/checkpoint references while avoiding image or private data leakage.

## Operator Actions

Inspect, resume, bounded retry, cancel, release stale lease, reconcile artifacts, and health commands require audit events. Dangerous actions support dry-run and confirmation.

## Soak Testing

Inject model/Lightroom termination, DB disconnect, disk pressure, stale locks, duplicate events, and partial files. Verify recovery and artifact integrity over repeated batches.

## Acceptance Checklist

- health and core metrics exist;
- faults are classified;
- operator actions are audited;
- no unbounded retry/wait exists;
- fault injection preserves integrity;
- release candidate also passes benchmark regression.

## T-030 Worker supervision rule

Worker heartbeat timeout, restart attempts, restart window, and shutdown timeout must be bounded. Tray survival does not authorize duplicate pipeline execution. Recovery uses durable checkpoints and idempotency evidence; crash-loop limits transition the Agent to explicit ERROR.

## T-031 Worker lifecycle operations

Supervise the inference child with heartbeat, bounded restart, idle timeout, crash-loop detection, and orphan cleanup. Distinguish watcher health from inference-worker residency.

## T-032 Planner Service Operations

Monitor API liveness/readiness, request latency, status/error classes, replay/conflict counts, rate limits, idempotency backend health, certificate expiry, and Planner/policy/schema versions. Do not log API keys or full private payloads. Client and server restart/replay tests are mandatory.
