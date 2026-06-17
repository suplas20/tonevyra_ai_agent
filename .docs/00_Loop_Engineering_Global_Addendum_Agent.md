# Tonevyra AI - Loop Engineering & Feedback Learning Addendum

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

## Purpose

Loop Engineering in Tonevyra AI is the operating design of the finished product agent. It is not a software development methodology.

The agent repeatedly observes work, decides the next safe step, executes it, verifies the result, recovers from failure, records evidence, and stores learning-ready feedback.

## Required Product Loops

```text
watch_loop
processing_loop
quality_loop
recovery_loop
feedback_loop
model_benchmark_loop
```

## Loop Definition Contract

Every autonomous behavior must define:

```text
entry condition
allowed actions
state transitions
retry limit
timeout
exit condition
failure condition
human review condition
persisted evidence
harness verification
```

The product must never run an open-ended loop without a termination rule.

## MVP Loop Evidence Storage

The current database contract does not create dedicated `loop_name` columns. For MVP, loop evidence is stored in `task_events.payload_json`.

Required payload keys for loop-related events:

```json
{
  "loop_name": "processing_loop",
  "loop_iteration": 1,
  "from_status": "QUEUED",
  "to_status": "ANALYZING",
  "reason": "worker picked task",
  "evidence_artifacts": []
}
```

If query-heavy dashboard requirements appear later, these fields may be promoted to first-class columns through Alembic migration.

## Required MVP Loops

### Watch Loop

```text
observe input folder
-> ignore hidden/temp/sidecar files
-> wait for file stabilization
-> register image_tasks row
-> record task_events row
-> continue watching until user stops the agent
```

### Processing Loop

```text
load task
-> preview
-> vision analysis
-> correction plan
-> Lightroom request/export
-> quality check
-> final status
```

### Quality Loop

```text
inspect exported image
-> score
-> write quality_detail artifact
-> write quality_results
-> decide PASS / REVIEW_REQUIRED / FAILED
```

### Recovery Loop

```text
load unfinished task
-> inspect DB status
-> verify artifact records and files
-> verify Lightroom response/export
-> choose safest resume point
-> record recovery decision
-> resume or fail safely
```

### Feedback Loop

```text
AI applied settings snapshot
-> user Lightroom behavior sync
-> current settings snapshot
-> hash comparison
-> manual_edit_delta artifact
-> feedback_records
-> learning_samples candidate
```

### Model Benchmark Loop

```text
candidate model test
-> memory/speed/quality comparison
-> benchmark artifact
-> promotion or rejection
```

## Feedback and Learning Policy

Allowed in MVP:

```text
store AI-applied Lightroom settings snapshot
store current Lightroom develop settings snapshot
compute manual edit delta
store explicit user feedback
register learning_samples candidates
```

Not allowed in MVP runtime:

```text
automatic online training
external training service
silent Qwen fine-tuning during photo processing
sending photos/previews/prompts/metadata/correction results/feedback externally
```

The first learning target is Correction Planner calibration and user style profiling. Direct VLM fine-tuning is future-only, offline, opt-in, versioned, benchmarked, and reversible.
