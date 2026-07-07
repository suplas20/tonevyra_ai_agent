# Resumable and Idempotent Jobs Skill

## Purpose

Use this skill for T-028 durable checkpoints, leases, heartbeats, stale-lock recovery, command idempotency, restart resume, and partial-commit reconciliation.

## Checkpoint Rule

Commit a checkpoint only after real output and artifact/DB evidence are valid. Do not advance state before the operation is durably proven.

## Mandatory Idempotency Boundaries

```text
analysis
adjustment plan
Lightroom apply
Lightroom export
artifact registration
quality decision
usage ledger commit
```

Duplicate keys return the existing result or current state; they do not execute the operation again.

## Lease Rule

Lease records require owner, acquire time, expiry, and heartbeat. Stale recovery must verify that the previous owner is no longer active before reassignment.

## Reconciliation

Handle file-created/DB-missing and DB-recorded/file-missing cases explicitly. Checksum mismatch is never silently repaired by overwriting trusted artifacts.

## Resume Rule

After restart, inspect checkpoint, pending command, external evidence, and idempotency result before deciding to resume, replay safely, or request manual intervention.

## Acceptance Checklist

- crash resumes from safe checkpoint;
- duplicate apply/export is prevented;
- stale leases are safely reclaimed;
- partial commits are classified/reconciled;
- retries/timeouts are bounded;
- usage commit remains exactly-once in effect.

## T-030 watcher idempotency rule

Created/Modified/Renamed/Moved-In/rescan events for one stable file must converge to one durable task and one external pipeline effect. Event coalescing is only the first layer; PostgreSQL transactional register-or-get-existing and existing idempotency keys remain authoritative across restart.

## T-032 Cross-network Idempotency

The Planner request is an idempotency boundary. Persist request body, input digest, request ID, and idempotency key before sending. Same key/same digest returns the committed result; same key/different digest is an integrity conflict. Server replay must not create a second Lightroom effect.
