# Cross-platform Installer Packaging Skill

## Purpose

Use this skill when packaging Tonevyra AI for Windows x64 and macOS Apple Silicon arm64, including one-click installation orchestration, installation state, payload layout, prerequisite automation and release artifacts.

## User Experience Contract

```text
installer launch
→ OS elevation/admin authentication
→ one Install action
→ automatic prerequisites, DB schema, plugin and startup configuration
→ post-install doctor
→ Tonevyra AI launch
```

Do not require the user to install Python/PostgreSQL manually, choose dependency versions, enter DB settings, execute SQL, run Alembic, copy a plugin or register startup.

## Mandatory Rules

- Preserve T-030 Windows and T-031 macOS runtime boundaries.
- Keep installer logic outside Agent business logic.
- Bundle Python 3.11.9; do not depend on system Python.
- Do not bundle PostgreSQL installers.
- Download and verify PostgreSQL, then install it unattended inside the same installer session.
- Automatically bootstrap the Tonevyra Role, database, Alembic schema and credentials.
- Keep Lightroom Classic external and user-managed; plugin installation is automatic when possible.
- Produce repair, upgrade and uninstall behavior.
- Persist resumable, idempotent installer state without secrets.
- Do not display install success before the post-install doctor passes.
- Separate reference evidence from real platform completion.

## Deliverables

```text
signed Windows installer
signed/notarized/stapled macOS package
all-in-one install orchestrator
DB bootstrap and schema automation
release manifest
payload hash inventory
third-party notices
live install evidence
```
