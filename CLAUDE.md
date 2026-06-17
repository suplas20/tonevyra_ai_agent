# CLAUDE.md

Read and follow `AGENTS.md` before making any code changes.

`AGENTS.md` is mandatory and has priority over all other project notes. After reading it, read the relevant `skills/*/SKILL.md` file for the implementation area.

Do not implement features outside MVP scope unless explicitly requested. If a request conflicts with `AGENTS.md`, stop and report the conflict instead of implementing it.

---

## Tonevyra AI naming rule

The current product name is Tonevyra AI.

Use these canonical names in new implementation:

```text
Product name: Tonevyra AI
Full technical name: Tonevyra AI Agent
Python package: tonevyra_agent
CLI command: tonevyra-agent
PostgreSQL database: tonevyra_agent
PostgreSQL app role: tonevyra_app
Primary DB env var: TONEVYRA_DATABASE_URL
Lightroom plugin folder: TonevyraAI.lrplugin
```

Do not introduce new `mw_photo_agent`, `MWPhotoAgent`, or `mw-agent` names in new code. Those are legacy references only. Temporary aliases may exist only for migration compatibility.

---

## Response language rule

User-facing explanations, progress updates, final reports, and implementation summaries must be written in Korean unless the user explicitly asks for another language.

Code identifiers, commands, file paths, logs, database object names, environment variable names, and quoted tool output may remain in their original language.

---

## Required reading for database work

Before implementing or modifying database, persistence, ORM, repository, migration, recovery, artifact metadata, or DB harness code, read:

```text
AGENTS.md
skills/postgresql-persistence/SKILL.md
skills/artifact-storage/SKILL.md
skills/testing-harness/SKILL.md
```

If a skill file is missing, stop and report that the required skill document is missing before implementing the area.

Database implementation rules:

```text
- Runtime app connection must use TONEVYRA_DATABASE_URL.
- Runtime app connection must use tonevyra_app, not postgres.
- tonevyra_agent is the single product database in MVP.
- The public schema contains the product tables.
- DBeaver SQL is bootstrap/inspection only.
- Future schema changes must be done through Alembic migrations.
- SQLAlchemy models must match the live PostgreSQL schema.
- Do not add SQLite as an operational fallback.
- Do not store image binaries, previews, exports, raw model payloads, or debug logs as DB blobs.
```

Required MVP database objects:

```text
image_tasks
task_artifacts
task_events
stage_results
quality_results
feedback_records
learning_samples
v_task_summary
```

---

## Required reading for autonomous agent behavior

Before implementing any autonomous behavior, retry behavior, watcher behavior, worker pipeline behavior, recovery behavior, quality decision behavior, feedback behavior, or model benchmark behavior, read:

```text
skills/loop-engineering/SKILL.md
skills/feedback-learning/SKILL.md
skills/testing-harness/SKILL.md
```

Loop engineering in this project means the finished product agent's automatic work-loop design. It does not mean the software development process.

Autonomous product behavior must be implemented as explicit bounded loops with:

```text
- entry condition
- allowed actions
- state transitions
- retry limit
- timeout
- exit condition
- failure condition
- human review condition
- persisted evidence
- harness verification
```

Do not create open-ended loops, unbounded retries, hidden background training, external training calls, or model fine-tuning during normal photo processing.

---

## Feedback learning rule

The system may collect local learning data from user feedback and user Lightroom behavior.

The first learning target is Correction Planner calibration. Direct vision-model fine-tuning is a later offline, opt-in, versioned, benchmarked, reversible process.

All feedback learning data must remain local. Do not send images, previews, prompts, metadata, correction results, manual edit deltas, feedback, or training candidates to external services.

MVP feedback implementation must stop at:

```text
- feedback_records persistence
- learning_samples candidate registration
- manual edit delta capture when available
- local dataset candidate artifact creation
```

Do not implement automatic fine-tuning in MVP.

---

## Required reading for model work

Before implementing a real model backend, read:

```text
AGENTS.md
skills/local-model-security/SKILL.md
skills/vision-analysis/SKILL.md
skills/testing-harness/SKILL.md
```

Model backend rules:

```text
- MockVisionBackend must pass before QwenVisionBackend is connected.
- Qwen is a replaceable backend candidate, not a hard dependency.
- Commercial default candidate: Qwen3-VL-4B-Instruct 4bit/GGUF.
- Commercial quality candidate: Qwen2.5-VL-7B-Instruct 4bit.
- Research-only / non-commercial reference: Qwen2.5-VL-3B-Instruct 4bit.
- Do not use Qwen2.5-VL-3B-Instruct as the commercial default unless a separate commercial license is obtained.
- Use local model files only.
- Use local_files_only=True.
- Do not use trust_remote_code=True.
- Do not download model files during photo processing.
- Do not call remote APIs.
- Do not load images from external URLs.
- Keep model worker network-blockable at OS firewall level.
- Do not silently promote or replace the default model without benchmark evidence and rollback path.
```

---

## Implementation behavior

When modifying code:

```text
1. Read AGENTS.md first.
2. Read the relevant skill file before editing.
3. Preserve the Tonevyra naming policy.
4. Keep the MVP CLI-first.
5. Keep worker concurrency at 1 unless AGENTS.md is explicitly updated.
6. Add or update tests/harness checks for the changed behavior.
7. Do not introduce dashboard, FastAPI-first, Redis, Celery, MinIO, message broker, or worker pool code in MVP.
8. Do not invent new status strings, stage strings, error codes, artifact types, or quality decisions without updating AGENTS.md, code enums, DB constraints, migrations, and tests together.
```

If implementation requires changing a project rule, stop and ask for approval before changing code.
