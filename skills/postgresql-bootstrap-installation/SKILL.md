# PostgreSQL Bootstrap Installation Skill

## Purpose

Use this skill for resolving, downloading, installing and fully bootstrapping the PostgreSQL instance used by Tonevyra without bundling the PostgreSQL installer or requiring manual database setup.

## Mandatory Rules

- Resolve the latest stable GA release through signed metadata.
- Reject alpha, beta, RC, snapshot and nightly artifacts.
- Download from an approved official source and verify SHA-256 plus publisher/package signature.
- Never bundle or redistribute the downloaded installer in the Tonevyra package.
- Install PostgreSQL unattended in the same Tonevyra installer session.
- Do not expose the PostgreSQL wizard or request DB version, port, role, database name or passwords from the user.
- Wait for PostgreSQL service readiness before DB work.
- Preserve existing PostgreSQL services, clusters and databases.
- Identify Tonevyra ownership explicitly.
- Create/verify `tonevyra_app` and `tonevyra_agent` idempotently.
- Restrict runtime DB access to localhost and least privilege; runtime role must not be superuser.
- Apply Alembic migrations transactionally to head.
- Verify required tables, view, indexes/constraints and schema revision.
- Execute a read/write smoke transaction and roll it back.
- Store credentials with DPAPI/Credential Manager on Windows or Keychain on macOS.
- Never write DB passwords or full connection URLs to logs, receipt or evidence.
- Preserve data on repair/uninstall.
- Do not silently perform PostgreSQL major upgrades.
- Do not start the Agent or report success until DB doctor passes.

## Required Objects

```text
image_tasks
task_artifacts
task_events
stage_results
quality_results
feedback_records
learning_samples
v_task_summary
alembic_version
```

## Evidence

Persist version resolution, source provenance, hash, signature, install receipt, service identity, DB connectivity, Role privilege, migration head, object verification, smoke transaction and credential-store result without storing passwords.
