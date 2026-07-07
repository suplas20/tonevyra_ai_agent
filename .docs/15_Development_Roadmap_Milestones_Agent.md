# Tonevyra AI - Development Roadmap & Milestones

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

## 1. Updated Roadmap

### Phase 1 - Project Bootstrap + DB Persistence

```text
src/tonevyra_agent skeleton
config/enums/errors
SQLAlchemy session
ORM models matching existing DB
repositories
tonevyra-agent doctor
DB smoke CRUD
```

### Phase 2 - Artifact Storage Foundation

```text
atomic write
checksum
artifact registration
artifact verification
```

### Phase 3 - Watcher + Preview + Mock Vision

```text
watch_loop
file stabilization
metadata extraction
1024px preview
mock vision structured output
```

### Phase 4 - Correction + Fake Lightroom + Quality

```text
correction planner
fake Lightroom bridge
fake export
quality gate
PASS/REVIEW_REQUIRED/FAILED persistence
```

### Phase 5 - End-to-End Worker Pipeline

```text
one photo end-to-end
required artifacts
required DB records
v_task_summary view usable
```

### Phase 6 - Recovery + Loop Event Verification

```text
recovery_loop
loop evidence in task_events.payload_json
retry limits
harness verification
```

### Phase 7 - Feedback Learning Foundation

```text
AI settings artifact
final settings artifact
manual_edit_delta artifact
feedback_records
learning_samples
feedback CLI skeleton
```

### Phase 8 - Real Lightroom Lua PoC

```text
TonevyraAI.lrplugin
PING
request/response
apply/export
settings snapshot support later
```

### Phase 9 - Local Qwen Backend

```text
Qwen2.5-VL 3B 4bit technical stable candidate
local-only
no trust_remote_code
offline env
model hash verification
```

### Phase 10 - Model Benchmark Loop

```text
compare Qwen2.5-VL 3B technical stable candidate and Qwen3-VL 4B commercial/default candidate
memory/speed/JSON stability/quality
promotion decision artifact
```

## 2. T-001 First Ticket

```text
T-001: Project Bootstrap + DB Persistence Foundation
```

Complete when:

```text
tonevyra-agent doctor passes
current_database = tonevyra_agent
current_user = tonevyra_app
required tables/view exist
DB smoke CRUD passes
no real Qwen/Lightroom code added
```

## 3. Do Not Start Yet

```text
React dashboard
FastAPI-first API
Redis/Celery/worker pool
MinIO/S3
real Qwen before mock pipeline
real Lightroom before fake bridge
automatic fine-tuning
```

## 4. Definition of MVP Done

```text
one supported image can be processed from input folder to final status
all required artifacts are durable and indexed
PostgreSQL stores final state
recovery resumes unfinished tasks
security harness passes
loop evidence is present
feedback storage foundation works
real Lightroom PoC passes
local Qwen backend works
```

---

## T-029 Roadmap Addendum

```text
T-029: Lightroom Native Mask Execution and Deterministic Radial Fallback
```

Deliverables:

```text
Phase 0 real-Lightroom radial preset proof
normalized mask request/result schemas
Mask Strategy Planner radial fallback
versioned/checksum radial template library
Plugin mask executor with snapshots, rollback, and idempotency
background-person red-recovery live evidence
static/runtime/strict-live harness gates
```

T-029 is complete only after the real Lightroom preset path retains geometry and the supplied small background-person case passes target recovery and spill-control validation.

## T-030 Roadmap Addendum

```text
T-030: Windows Background Watcher and System Tray Agent
```

Deliverables:

```text
per-user Tray Shell and Background Worker
single-instance guards
continuous folder watch with stability and event coalescing
PostgreSQL-backed idempotent task registration
pause/resume/rescan
Worker heartbeat and bounded restart
current-user autostart abstraction
graceful shutdown and restart recovery
Tonevyra tray icon asset contract
static/reference/implementation/Windows-live harness gates
```

T-030 is complete only after actual Windows live evidence proves the tray, stable-file gating, deduplication, pause/resume, Worker crash recovery, source integrity, and zero orphan processes.

## T-032 Milestone Addendum

T-032 is complete only after Planner extraction, API client/service implementation, secure deployment, client build rule exclusion, live HTTPS/idempotency/restart evidence, 3000 sequential soak, and T-019~T-031 regressions. Otherwise report the exact BLOCKED gate.
