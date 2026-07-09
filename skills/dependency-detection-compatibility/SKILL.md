# Dependency Detection and Compatibility Skill

## Purpose

Use this skill to detect OS, architecture, bundled runtime integrity, PostgreSQL ownership/version, Lightroom presence and prerequisite compatibility without damaging user-managed software.

## Detection Rules

- A command found in PATH is not sufficient evidence.
- Verify executable identity, architecture, version and ownership.
- Never replace a user Python or generic PostgreSQL instance silently.
- Distinguish Tonevyra-owned, compatible external, incompatible and absent states.
- Lightroom absence must not block base installation.
- Use a persisted compatibility matrix and stable error codes.

## Failure

Ambiguity is a recoverable stop with diagnostics, not permission to guess paths, credentials, ports or service ownership.
