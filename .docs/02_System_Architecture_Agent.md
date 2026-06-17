# Tonevyra AI - ?꾩껜 ?쒖뒪??援ъ“

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
FastAPI-first architecture
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

## 1. Architecture

Tonevyra AI is a local orchestrated pipeline.

```text
CLI / Main
-> Agent Core
   -> Watcher
   -> Worker
   -> Recovery
   -> Images
   -> Vision
   -> Correction Planner
   -> Lightroom Bridge
   -> Quality Gate
   -> Learning/Feedback
-> PostgreSQL + Artifact Storage
```

The Python agent is the orchestrator. UI cannot own business logic.

## 2. MVP Runtime Processes

```text
PostgreSQL local server
Python Tonevyra agent
Lightroom Classic + Lua plugin later
```

During early MVP:

```text
PostgreSQL local server
Python Tonevyra agent
Mock Vision backend
Fake Lightroom backend
```

## 3. Process Flow

```text
watch
-> stabilize
-> create task
-> create 1024px preview
-> vision
-> correction
-> Lightroom request
-> export
-> quality
-> final status
```

## 4. Module Boundaries

```text
agent/       orchestration only
images/      metadata and preview
vision/      model analysis and schema validation
correction/  safe Lightroom plan generation
lightroom/   JSON bridge only
quality/     exported image scoring
learning/    feedback capture and dataset candidates
db/          SQLAlchemy and repositories
storage/     atomic artifact files
core/        config, enums, errors
```

## 5. Loop Engineering Layer

Loop Engineering is a design rule, not a separate microservice.

```text
Folder Watcher   -> watch_loop
Agent Worker     -> processing_loop
Quality Gate     -> quality_loop
Recovery Manager -> recovery_loop
Lightroom Sync   -> feedback_loop
Benchmark Runner -> model_benchmark_loop
```

Loop state is persisted through `image_tasks`, `task_events`, `stage_results`, and `task_artifacts`. File logs are never loop memory.

## 6. Deferred Architecture

Do not introduce FastAPI, React dashboard, Redis, Celery, MinIO, or worker pools before the CLI pipeline and recovery work correctly.
