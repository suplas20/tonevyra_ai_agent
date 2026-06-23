# Usage and Cost Control Skill

## Purpose

Use this skill for T-027 quota reservation, idempotent usage ledger, commit/release rules, compute telemetry, and duplicate-charge prevention.

## Ledger State

```text
RESERVED → COMMITTED
         → RELEASED
```

## Idempotency

Each event requires a stable idempotency key. Duplicate reserve/commit/release operations must not change totals more than once.

## Retry Accounting

A quality retry does not consume another photo unit. It may add compute metrics. Technical failures, cancellations, fallback, and partial batches follow explicit versioned policy.

## Separation

Track customer usage units separately from internal compute cost estimates. Do not infer billing amounts from raw GPU time without a product pricing policy.

## Isolation

Quota and ledger entries are isolated by user scope. Cross-user aggregation may exist only in authorized operational summaries without changing ownership.

## Acceptance Checklist

- quota boundaries are exact;
- duplicate events are idempotent;
- retries do not double-count photos;
- reserve/commit/release reconcile;
- user scopes do not mix;
- fallback and resource metrics are auditable.
