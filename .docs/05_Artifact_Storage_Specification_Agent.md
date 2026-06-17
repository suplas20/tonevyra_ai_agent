# Tonevyra AI - ?곗텧臾???μ냼

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

## 1. Interface Rule

All modules must use `ArtifactStorage.save/load/exists/verify`.

Business modules must not write artifact files directly.

## 2. Artifact Root

```text
runtime/artifacts/
runtime/previews/
runtime/bridge/
```

Recommended per-task layout:

```text
runtime/artifacts/{task_id}/
  exif.json
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

The previous `{job_id}/{task_id}` path is deferred because current MVP schema does not include `jobs`.

## 3. Atomic Write

Required order:

```text
1. Write .tmp file in same directory.
2. Flush.
3. fsync when possible.
4. Atomic rename to final path.
5. Calculate sha256 and size.
6. Insert/update task_artifacts.
7. Insert stage_results/task_events and update image_tasks in one DB transaction.
```

## 4. Artifact Types

Use names aligned with DB CHECK constraints:

```text
EXIF_JSON
PREVIEW_JPEG
VISION_PROMPT
VISION_RAW_RESPONSE
VISION_STRUCTURED
CORRECTION_PLAN
LIGHTROOM_REQUEST
LIGHTROOM_RESPONSE
QUALITY_DETAIL
EXPORTED_IMAGE
AI_SETTINGS
FINAL_SETTINGS
MANUAL_EDIT_DELTA
FEEDBACK_RECORD
```

## 5. Loop and Feedback Artifacts

Loop evidence may be stored as:

```text
loop_trace.json
retry_history.json
recovery_decision.json
model_benchmark_result.json
```

Feedback/learning evidence:

```text
ai_applied_develop_settings.json
ai_applied_develop_hash.txt
current_develop_settings.json
current_develop_hash.txt
manual_edit_delta.json
user_feedback.json
training_sample_manifest.json
```

If an artifact type is not in the current DB CHECK constraint, store it under the closest supported artifact type and include the specific subtype in artifact metadata or file name, or add a future Alembic migration after approval.

## 6. Future Backend

Keep the storage interface replaceable for MinIO/S3 later, but do not implement those backends in MVP.
