# Tonevyra AI - Testing & QA Strategy

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

## 1. Unit Tests

Required early unit tests:

```text
core enums/status validation
config loading
repository CRUD
artifact atomic write
checksum verification
schema validators
planner clamp
quality threshold decision
state transition helpers
```

## 2. Integration Tests

Use PostgreSQL + local artifacts + mock/fake backends.

```text
Mock Vision
Fake Lightroom
Artifact Storage
DB repositories
Worker Pipeline
```

## 3. Harness Gates

A feature is not complete until its harness or equivalent test passes.

Required harness checks:

```text
Security Harness
Smoke Pipeline
Artifact Verify
DB State Verify
Recovery Harness
Watcher Harness
Loop Event Verify
Feedback Verify
```

## 4. Loop Verification

Testing must verify loops, not only file existence.

Checks:

```text
watch_loop ignores sidecars/temp files
processing_loop reaches final status
quality_loop produces PASS/REVIEW_REQUIRED/FAILED
recovery_loop resumes seeded incomplete states
feedback_loop stores feedback structures
model_benchmark_loop compares candidates without changing default
retry limits prevent infinite loops
```

Because current DB stores loop data in `task_events.payload_json`, verification must inspect payload keys:

```text
loop_name
loop_iteration
from_status
to_status
reason
```

## 5. DB Verification

Doctor and DB tests must confirm:

```text
current_database() = tonevyra_agent
current_user = tonevyra_app
required tables exist
v_task_summary exists
test task can be created/read/deleted
```

## 6. Lightroom Tests

Real Lightroom tests come after fake bridge passes:

```text
plugin load
PING
request read
apply adjustments
export
response write
settings snapshot read for future feedback sync
```

## 7. Quality Evaluation

Track false PASS and false REVIEW. Human review is needed before tuning thresholds.

---

## T-029 Testing Addendum

T-029 requires four test layers:

```text
static contract/schema/fixture validation
deterministic geometry/template-selection runtime harness
fake Plugin failure/idempotency/rollback tests
real Lightroom Phase 0 and target-image live validation
```

The supplied underwater image is the canonical regression case for native target-detection failure and upper-left radial fallback. Strict completion also requires all T-019 through T-028 regression gates.

## T-030 Windows Background/Tray QA Addendum

Required test classes:

```text
unit: coalescer, stability, exclusion, identity, state reducer
integration: PostgreSQL idempotent registration, pause/resume/rescan
Windows: named mutex, named pipe, tray lifecycle, autostart, shutdown
recovery: Worker crash, heartbeat timeout, restart limit, no duplicate effects
soak: long idle watch and 100+ sequential files
```

Headless reference tests do not replace Windows live evidence. Production completion requires approved icon assets, visible tray proof, copy-in-progress proof, single-instance proof, crash recovery, and zero orphan processes.
