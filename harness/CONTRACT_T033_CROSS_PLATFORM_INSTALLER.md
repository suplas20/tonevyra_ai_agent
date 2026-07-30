# CONTRACT — T-033 Cross-platform All-in-One Installer Packaging

## Required product behavior

```text
single installer artifact per platform
one Install action plus OS elevation/admin authentication
Windows x64 installer
macOS arm64 PKG/DMG
bundled Python 3.11.9
PostgreSQL installer absent from package
latest stable PostgreSQL downloaded from approved official source
PostgreSQL unattended installation
Tonevyra Role/DB automatic bootstrap
Alembic schema automatic installation/upgrade
schema/privilege/read-write verification
secure DB credential storage
Lightroom external/user-managed; plugin automatic or PENDING
Agent startup automatic
post-install doctor before success
repair, upgrade, uninstall
release signing and macOS notarization
```

## Required static invariants

- T-032 baseline files remain.
- At least 58 cumulative skills exist.
- T-033 inventory snapshot contains exactly 58 skills.
- Required T-033 documents, skills, schemas, fixtures and scripts exist.
- Python distribution is `bundled`, version policy is exact `3.11.9`.
- PostgreSQL distribution is `download`, `bundled=false`, `channel=latest-stable`.
- PostgreSQL prerelease is forbidden.
- Lightroom is external and not required for base installation.
- Artifact scan must prove that no PostgreSQL installer is bundled.
- Normal installation requires zero manual prerequisite steps and zero manual database steps.
- Database bootstrap must be idempotent and non-destructive.
- The Agent cannot start and install cannot complete before DB/schema/post-install doctor success.

## Required database objects

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

## Strict completion evidence

```text
implementation runtime evidence
all-in-one installation evidence
DB bootstrap/schema evidence
real Windows installation evidence
real macOS signed/notarized installation evidence
final package artifact scan
T-019 through T-032 regression summary
```

Reference harness evidence cannot satisfy strict completion.
