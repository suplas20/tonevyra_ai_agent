# Tonevyra AI - Agent Core State Machine

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

## 1. Statuses

Use only canonical statuses:

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

## 2. Stages

```text
watch
metadata
preview
vision
correction_plan
lightroom
export
quality
feedback
recovery
```

## 3. Worker Defaults

```text
model_worker = 1
lightroom_worker = 1
```

Do not introduce complex worker pools in MVP.

## 4. Transition Rule

Stage transition order:

```text
stage work
-> artifact save
-> task_artifacts insert/update
-> stage_results insert/update
-> task_events insert
-> image_tasks status/current_stage update
-> commit
```

DB must not claim a stage succeeded before durable artifacts exist.

## 5. Retry

Retry must be bounded.

Each retry must record:

```text
image_tasks.retry_count
task_events event
retry_history.json or payload_json evidence
structured error_code when applicable
```

## 6. Loop Evidence

For MVP, loop evidence is stored in `task_events.payload_json`.

Example:

```json
{
  "loop_name": "quality_loop",
  "loop_iteration": 1,
  "from_status": "QUALITY_CHECK",
  "to_status": "REVIEW_REQUIRED",
  "reason": "overall_score below pass threshold"
}
```

## 7. Feedback Loop Status Rule

Feedback Loop should not change final task status by default. It creates feedback and learning records. Any planner calibration update requires explicit local approval, versioning, and rollback capability.

## T-030 Agent Runtime State Addendum

Agent process state is separate from photo task state:

```text
STARTING → WATCHING ↔ PROCESSING
WATCHING/PROCESSING → PAUSED → WATCHING
any live state → DEGRADED → WATCHING/PROCESSING
fatal operational condition → ERROR
any live state → STOPPING → STOPPED
```

These values must not be written into `image_tasks.status`. Runtime snapshots and task/incident evidence carry them.

## T-032 Planner API State Addendum

No new canonical status is introduced. Transient Planner API attempts occur while the task remains `ANALYSIS_DONE`. Successful validated response transitions to `CORRECTION_PLANNED`. Exhausted/non-retryable failures transition using existing failure policy with explicit `PLANNER_API_*` evidence.
