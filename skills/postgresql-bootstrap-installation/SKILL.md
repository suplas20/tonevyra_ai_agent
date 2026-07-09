# PostgreSQL Bootstrap Installation Skill

## Purpose

Use this skill for resolving, downloading, installing and bootstrapping the PostgreSQL instance used by Tonevyra without bundling the PostgreSQL installer.

## Mandatory Rules

- Resolve the latest stable GA release through signed metadata.
- Reject alpha, beta, RC, snapshot and nightly artifacts.
- Download from an approved official source and verify SHA-256 plus publisher/package signature.
- Never bundle or redistribute the downloaded installer in the Tonevyra package.
- Preserve existing PostgreSQL services, clusters and databases.
- Identify Tonevyra ownership explicitly.
- Restrict runtime DB access to localhost and least privilege.
- Apply migrations transactionally and preserve data on repair/uninstall.
- Do not silently perform PostgreSQL major upgrades.

## Evidence

Persist version resolution, source provenance, hash, signature, install receipt, service identity, DB connectivity and migration head without storing passwords.
