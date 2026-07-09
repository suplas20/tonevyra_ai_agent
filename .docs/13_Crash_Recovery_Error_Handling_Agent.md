# Tonevyra AI - Crash Recovery & Error Handling

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

## 1. Recovery Inputs

Recovery must inspect:

```text
image_tasks.status
image_tasks.current_stage
task_artifacts records
artifact file existence
artifact checksums
Lightroom response file existence
export file existence
stage_results
task_events
```

Logs are not recovery source.

## 2. Startup Recovery

On startup:

```text
load unfinished tasks
inspect current status
verify expected artifacts
verify bridge response/export files
choose safest resume point
record recovery event
resume or fail safely
```

## 3. Recovery Examples

```text
ANALYZING + VISION_STRUCTURED artifact exists
-> resume correction planning

LIGHTROOM_REQUESTED + lightroom_response exists
-> process Lightroom response

EXPORT_DONE + exported image exists
-> resume quality check

PASS but export missing
-> mark FAILED or schedule explicit re-export after approval
```

## 4. Error Codes

Use controlled error codes:

```text
FILE_NOT_STABLE
UNSUPPORTED_FILE_TYPE
PREVIEW_GENERATION_FAILED
MODEL_LOAD_FAILED
MODEL_INFERENCE_FAILED
MODEL_OUTPUT_INVALID
CORRECTION_PLAN_FAILED
LIGHTROOM_REQUEST_FAILED
LIGHTROOM_RESPONSE_TIMEOUT
LIGHTROOM_EXPORT_FAILED
EXPORT_FILE_MISSING
QUALITY_CHECK_FAILED
ARTIFACT_WRITE_FAILED
DB_WRITE_FAILED
SECURITY_NETWORK_ACCESS_BLOCKED
```

Do not invent arbitrary strings.

## 5. Failure Storage

Each failed task must store:

```text
error_code
error_message
failed_stage
retry_count
updated_at
```

## 6. Recovery Loop

Recovery is an explicit loop:

```text
load unfinished task
-> inspect evidence
-> decide resume/fail/review
-> record recovery_decision artifact or task_event payload
-> execute safe next action
-> stop with clear result
```

If evidence is inconsistent, move to `FAILED` or `REVIEW_REQUIRED` with structured error.

## T-030 Worker Supervision and Session Shutdown Addendum

The Tray Shell monitors a bounded Worker heartbeat. A missing heartbeat records an incident and may trigger a limited restart. Restart limits prevent crash loops. Recovery resumes from T-028 checkpoints and must not duplicate Lightroom apply/export effects.

Graceful exit sequence:

```text
stop intake
→ checkpoint/cancel active stage safely
→ flush DB/artifact/runtime evidence
→ close watcher and IPC
→ join Worker with timeout
→ remove tray icon
```

Forced process termination is not the normal shutdown path. After abnormal termination, the next run reconciles incomplete jobs through the existing recovery loop.

## T-032 Recovery Addendum

Recover from the persisted Planner request and stable idempotency key. Do not regenerate a changed request under the same key. Network/408/429/5xx may retry within policy; auth/schema/privacy/digest/version/conflict failures require explicit remediation or a new valid attempt.

## T-033 Installer Failure Recovery

Installer download, prerequisite, migration and payload replacement failures use stable `T033-*` error codes, redacted logs and bounded rollback. Existing application and database state must remain usable or explicitly reported as requiring manual recovery.
