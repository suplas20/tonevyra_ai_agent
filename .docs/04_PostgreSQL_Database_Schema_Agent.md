# Tonevyra AI - PostgreSQL DB ?ㅽ궎留?
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

## 1. Database Bootstrap

Canonical local DB setup:

```text
Admin role: postgres
App role: tonevyra_app
Database: tonevyra_agent
Schema: public
Runtime env: TONEVYRA_DATABASE_URL
```

Application code must connect as `tonevyra_app`, not `postgres`.

## 2. Current MVP Objects

```text
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

This is the canonical schema for T-001.

## 3. Table Responsibilities

### image_tasks

Source of truth for one-photo task status.

Key fields:

```text
id
source_path
source_hash
file_name
file_ext
file_size_bytes
status
current_stage
error_code
error_message
failed_stage
retry_count
overall_score
quality_decision
created_at
updated_at
completed_at
```

### task_artifacts

Indexes durable artifact files.

Key fields:

```text
task_id
artifact_type
artifact_path
sha256
size_bytes
mime_type
version
created_at
```

### stage_results

Stores stage-level summary and timing.

Key fields:

```text
task_id
stage
stage_status
summary_json
started_at
finished_at
duration_ms
```

### task_events

Records status changes, loop events, recovery events, and failure/human-review events.

Current MVP fields:

```text
task_id
event_type
stage
message
payload_json
created_at
```

Loop evidence must be stored in `payload_json`:

```json
{
  "loop_name": "processing_loop",
  "loop_iteration": 1,
  "from_status": "ANALYZING",
  "to_status": "ANALYSIS_DONE",
  "reason": "vision structured artifact saved"
}
```

### quality_results

Stores quality gate result.

```text
exposure_score
color_score
sharpness_score
noise_score
saturation_score
underwater_cast_score
overall_score
decision
reason_summary
detail_json
```

### feedback_records

Stores local user feedback and manual edit comparison.

```text
user_action
rating
reason_tags
ai_settings_json
final_settings_json
manual_edit_delta_json
accepted
```

### learning_samples

Stores future learning candidate metadata.

```text
sample_type
sample_status
dataset_path
metadata_json
```

## 4. Deferred Tables

Do not create these in MVP unless explicitly requested through migration:

```text
jobs
images
vision_analyses
correction_plans
lightroom_requests
manual_edit_records
style_profiles
training_samples
```

`training_samples` from older docs is now represented by `learning_samples`.

## 5. Migration Rule

The DBeaver-created schema is the initial bootstrap state. After implementation starts:

```text
- SQLAlchemy models must match current DB.
- Alembic must manage future schema changes.
- No direct manual schema edits in DBeaver during implementation.
- No destructive migration without explicit approval.
```

## 6. Required Verification Queries

```sql
SELECT current_database(), current_user;

SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_type, table_name;
```

Expected DB/user:

```text
tonevyra_agent | tonevyra_app
```
