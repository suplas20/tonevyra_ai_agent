# PostgreSQL Database Schema - DB 스키마

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Tables

jobs, images, image_tasks, vision_analysis, correction_plans, lightroom_requests, quality_results, task_artifacts, task_events, app_settings.

## 2. Use JSONB Carefully

Use JSONB for summary_jsonb and adjustments_jsonb, not for large raw payloads.

## 3. Required Indexes

image_tasks(status), image_tasks(job_id), image_tasks(updated_at), quality_results(decision), task_events(task_id, created_at).

## 4. Do Not

Do not store image binaries. Do not create excessive JSONB indexes. Do not write every progress tick.

## 5. Migration

Use SQLAlchemy 2.0 + Alembic. All schema changes must be migrations.

## Implementation Guardrails

- Do not build the full React dashboard before the agent core is stable.
- Do not replace PostgreSQL with SQLite.
- Do not store image binaries in PostgreSQL.
- Do not store heavy raw model payloads in PostgreSQL unless explicitly requested.
- Do not make high-quality preview or 7B model mandatory in MVP.
- Do not let the model directly edit images or bypass Correction Planner.
- Do not skip artifact persistence or crash recovery.

---

<!-- LOOP_ENGINEERING_UPDATE_V3 -->

## Loop Engineering and Learning Tables

The schema must support explicit product loops.

Required additions or extensions:

```text
task_events:
  loop_name
  loop_iteration
  event_type
  from_status
  to_status
  reason

manual_edit_records:
  task_id
  ai_applied_hash
  current_hash
  manual_edit_detected
  changed_fields
  delta_summary
  checked_at

feedback_records:
  task_id
  user_decision
  rating
  reason_tags
  use_current_settings_for_learning
  created_at

training_samples:
  task_id
  preview_artifact_id
  analysis_artifact_id
  correction_plan_artifact_id
  feedback_artifact_id
  approved_for_training
  created_at

style_profiles:
  profile_name
  scene_type
  preferred_adjustments
  confidence
  updated_at
```

MVP may create only the minimal subset needed for feedback collection, but the schema must not block later learning.

---

## Commercial Model Policy Update - Qwen3 Default

Tonevyra AI uses a commercial-safe local model policy.

```text
Commercial default vision model candidate:
Qwen3-VL-4B-Instruct 4bit/GGUF

Commercial quality candidate:
Qwen2.5-VL-7B-Instruct 4bit, hardware permitting

Research/non-commercial reference only:
Qwen2.5-VL-3B-Instruct 4bit
```

Rules:

```text
- Qwen3-VL-4B-Instruct 4bit/GGUF is the commercial default candidate, subject to local benchmark validation.
- Qwen2.5-VL-7B-Instruct 4bit may be evaluated as a quality candidate when hardware allows.
- Qwen2.5-VL-3B-Instruct must not be used as the commercial default unless a separate commercial license is obtained.
- All model inference must remain local-only and offline-capable.
- The model may receive only 1024px sRGB JPEG preview + EXIF/basic metadata.
- The model must not receive original RAW files, Lightroom catalog files, private DB dumps, unrelated user files, or external URLs.
- Model loading must use local files only, no runtime downloads, no remote API fallback, and no `trust_remote_code=True`.
```



---

## Model License Verification Rule

Before real model deployment or public/commercial distribution, the agent or developer must re-check the live model card and license file for the selected model and record:

```text
model_id
model_version_or_revision
local_path
license
sha256 or verified file hash
commercial_allowed flag
verification_date
```

Do not assume that a model license remains unchanged across revisions.
