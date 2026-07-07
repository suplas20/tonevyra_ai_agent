# Tonevyra AI - CLI Operations

> Agent-readable implementation document. Follow `AGENTS.md` first, then `CLAUDE.md`, then this document.

Version: v2.0-tonevyra  
Product: Tonevyra AI  
Scope: Local AI photo correction agent MVP  
Primary package: `tonevyra_agent`  
CLI: `tonevyra-agent`  
Database: `tonevyra_agent`  
Application DB role: `tonevyra_app`  
Schema: `public`

---

## Global MVP Decisions

```text
Product name: Tonevyra AI
Package: src/tonevyra_agent/
CLI command: tonevyra-agent
PostgreSQL database: tonevyra_agent
PostgreSQL app role: tonevyra_app
Runtime DB env: TONEVYRA_DATABASE_URL
Main DB: PostgreSQL
Detailed outputs: local Artifact Storage
Model input: 1024px sRGB JPEG preview + EXIF/basic metadata
Technical stable candidate: Qwen2.5-VL 3B 4bit
Commercial/default candidate: Qwen3-VL 4B 4bit
Debug traces: file logs only
```

Deferred from MVP:

```text
React dashboard
FastAPI-first local Agent architecture (dedicated T-032 Planner Service excepted)
Redis / Celery / MinIO / worker pools
SaaS account system
2048px multi-crop as default
Lightroom neutral preview as default
Qwen 7B/8B as default
Automatic model fine-tuning during normal processing
External training service
```

## Canonical MVP Database Contract

Use the already-created PostgreSQL objects as the implementation contract.

```text
Database: tonevyra_agent
Role used by app: tonevyra_app
Schema: public

Tables:
- image_tasks
- task_artifacts
- task_events
- stage_results
- quality_results
- feedback_records
- learning_samples

View:
- v_task_summary

Extension/function:
- pgcrypto
- public.set_updated_at()
```

Rules:

```text
- Do not use the postgres superuser for normal app runtime.
- Do not create separate databases for artifacts, stages, quality, feedback, or learning.
- Do not replace PostgreSQL with SQLite.
- Do not store original images, exports, previews, or large raw payloads as DB blobs.
- After implementation starts, schema changes must be managed through Alembic migrations.
```

## Canonical Status Values

```text
DETECTED
STABILIZING
QUEUED
ANALYZING
ANALYSIS_DONE
CORRECTION_PLANNED
LIGHTROOM_REQUESTED
LIGHTROOM_PROCESSING
EXPORT_DONE
QUALITY_CHECK
PASS
REVIEW_REQUIRED
FAILED
SKIPPED
```

Final statuses:

```text
PASS
REVIEW_REQUIRED
FAILED
SKIPPED
```

Do not invent additional status strings.

---

## 1. CLI Name

Use:

```bash
tonevyra-agent
```

Do not create new MVP commands under `mw-agent` unless a compatibility alias is explicitly requested.

## 2. Required MVP Commands

```bash
tonevyra-agent init
tonevyra-agent doctor
tonevyra-agent start
tonevyra-agent stop
tonevyra-agent status
tonevyra-agent tasks --status STATUS
tonevyra-agent task TASK_ID
tonevyra-agent scan
tonevyra-agent retry TASK_ID
tonevyra-agent process FILE_PATH
tonevyra-agent test-lightroom
tonevyra-agent test-vision
```

## 3. CLI Rule

CLI must call clean interfaces. It must not contain business logic, raw SQL, model internals, artifact write internals, or Lightroom Lua logic.

## 4. Doctor Requirements

`doctor` must verify:

```text
Python version is 3.11.x
runtime folders exist
TONEVYRA_DATABASE_URL is set
PostgreSQL connection works
current_database() = tonevyra_agent
current_user = tonevyra_app
required tables exist
v_task_summary exists
artifact root is writable
bridge folders exist
mock vision backend can load
fake Lightroom backend can run when configured
```

## 5. Loop Visibility Commands

Recommended after core pipeline:

```bash
tonevyra-agent loop-status
tonevyra-agent loop-events TASK_ID
tonevyra-agent feedback sync TASK_ID
tonevyra-agent feedback approve TASK_ID
tonevyra-agent feedback reject TASK_ID --reason too_blue
tonevyra-agent benchmark-models --sample-set harness
```

These commands must not implement loop business logic directly. They call agent/recovery/lightroom/learning/benchmark/db modules.

## T-030 Background/Tray CLI Addendum

Add or extend commands without removing existing CLI behavior:

```text
tonevyra-agent background
tonevyra-agent tray
tonevyra-agent status
tonevyra-agent watch pause
tonevyra-agent watch resume
tonevyra-agent watch rescan
tonevyra-agent startup enable
tonevyra-agent startup disable
tonevyra-agent startup status
```

CLI and Tray use the same validated Worker command interface. CLI must not bypass idempotency, recovery, or audit evidence.

## T-032 CLI Addendum

Add safe operator commands for Planner connectivity/version/health and bounded retry inspection. CLI output must redact keys and payloads. A connectivity test may send a non-photo synthetic contract request, but it must not bypass normal auth/TLS validation.
