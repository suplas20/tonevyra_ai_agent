# Tonevyra AI - ??μ냼 ?꾨왂

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

## 1. Source of Truth

```text
PostgreSQL = operational state source of truth
Artifact Storage = detailed output/evidence source of truth
File logs = debug traces only
```

Recovery must use DB state and artifact/export/response existence, not logs.

## 2. PostgreSQL Stores

```text
task state
current stage
retry count
error code
quality summary
artifact index
stage summary
task events
feedback summary
learning sample candidate metadata
```

## 3. Artifact Storage Stores

```text
exif.json
preview.jpg
vision_prompt.txt
vision_raw_response.json
vision_structured.json
correction_plan.json
lightroom_request.json
lightroom_response.json
quality_detail.json
retry_history.json
loop_trace.json
user_feedback.json
manual_edit_delta.json
```

## 4. Do Not Store in PostgreSQL

```text
original image binaries
exported image binaries
preview binaries
large raw model payloads by default
full OpenCV debug dumps
file logs
```

## 5. Current DB Contract

Use only the created MVP objects:

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

Old design-table names such as `jobs`, `images`, `vision_analyses`, `correction_plans`, `lightroom_requests`, `manual_edit_records`, `style_profiles`, and `training_samples` are deferred. Their information is represented through current tables and artifacts until migration is justified.

## 6. Loop and Learning Persistence

Loop evidence must be stored in `task_events.payload_json` for MVP.

Feedback learning data must remain local and use:

```text
feedback_records
learning_samples
task_artifacts
```

The first learning use case is Correction Planner calibration and user style profile derivation. Direct model fine-tuning is not MVP runtime behavior.

## T-032 Persistence Addendum

Persist `planner_request.json`, `planner_response.json`, `planner_api_attempts.json`, and `correction_plan.json` atomically with checksums. Do not persist API keys or Authorization headers. Request ID, input digest, idempotency key hash/reference, attempt count, result/error class, and Planner/policy versions must be recoverable.
