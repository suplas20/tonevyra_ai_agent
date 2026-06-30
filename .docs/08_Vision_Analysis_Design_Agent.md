# Tonevyra AI - Vision Analysis Design

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

## 1. Role

The vision model diagnoses image issues. It does not edit images and does not directly control Lightroom.

Correct flow:

```text
preview + metadata
-> vision analysis
-> structured result
-> correction planner
-> clamped Lightroom plan
```

Wrong flow:

```text
model raw output
-> uncontrolled Lightroom values
-> direct apply
```

## 2. MVP Input

```text
1024px sRGB JPEG preview
EXIF/basic metadata
```

Original RAW/JPG is not sent directly to the model.

## 3. Backends

Required:

```text
MockVisionBackend
QwenVisionBackend interface only until mock pipeline passes
```

Technical stable candidate after mock pipeline:

```text
Qwen2.5-VL 3B 4bit
```

Commercial/default candidate:

```text
Qwen3-VL 4B 4bit
```

Qwen3-VL 4B 4bit promotion requires license review, local benchmark evidence, rollback documentation, and explicit human approval.

## 4. Output Schema

Structured output should include:

```text
scene_type
main_subject
usable
issues
edit_intent
confidence
risk_flags
```

## 5. Artifact Flow

```text
vision_prompt.txt
vision_raw_response.json
vision_structured.json
```

DB stores summary in `stage_results.summary_json` and events in `task_events`. Raw response remains an artifact.

## 6. Model Security

```text
local model files only
local_files_only=True
trust_remote_code=True prohibited
no runtime model download
no remote API calls
no external image URLs
telemetry disabled where possible
outbound network blockable
```

## 7. Learning Boundary

The vision model is not self-training in MVP runtime.

Allowed:

```text
collect approved samples locally
benchmark candidate models
store raw/structured outputs as artifacts
```

Not allowed:

```text
online model training
silent fine-tuning while processing photos
external training service
```

---

## T-029 Target Geometry Addendum

For local fallback planning, Vision/Semantic Analysis may emit an oriented normalized target geometry and detection-risk evidence.

```text
region_id
semantic_type
confidence
coordinate_space = oriented_normalized_image
center_x / center_y / width / height / rotation_deg
native_detection_risk
color_loss diagnosis
recommended intent
```

It must not emit template IDs, preset paths, Plugin commands, final Lightroom values, or UI coordinates. Geometry must describe the visual target after EXIF orientation is applied.
