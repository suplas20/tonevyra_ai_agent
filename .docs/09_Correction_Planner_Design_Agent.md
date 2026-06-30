# Tonevyra AI - Correction Planner Design

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

Correction Planner converts validated vision analysis into safe Lightroom adjustment plans.

Inputs:

```text
VisionAnalysisResult
EXIF/basic metadata
retry history
quality feedback if retrying
future user style calibration
```

Outputs:

```text
base_preset
style_target
adjustments_json
confidence
requires_review
reason_summary
```

## 2. Safety Rule

The planner must clamp all Lightroom parameters to allowed ranges before sending to Lightroom.

The model output is advisory only.

## 3. Artifact Flow

```text
correction_plan.json
```

Register as artifact type:

```text
CORRECTION_PLAN
```

Store summary in `stage_results.summary_json`.

## 4. Review Triggers

The planner must mark `requires_review` when:

```text
vision confidence is low
scene usability is poor
risk flags are severe
needed adjustment exceeds safe clamp
image appears damaged/corrupted
```

## 5. Retry

Retry correction must be bounded. Record retry reason and previous quality result in artifact or task event payload.

## 6. Planner Calibration

Correction Planner is the first learning target.

Feedback examples:

```text
AI too blue -> user warmed Temperature
AI too dark -> user raised Exposure
AI over-dehazed -> user reduced Dehaze
```

MVP stores deltas in `feedback_records` and `MANUAL_EDIT_DELTA` artifacts. It must not silently rewrite planner rules. Calibration requires explicit local approval, versioning, and rollback.

---

## T-029 Mask Strategy Planner Addendum

The Planner gains a deterministic mask-strategy stage:

```text
semantic target
→ confidence/geometry validation
→ runtime capability snapshot
→ native target-detection evidence
→ radial template fit search when native fails
→ bounded local values
→ mask execution plan
```

Template selection records center distance, coverage, overflow, aspect error, size error, fit score, policy version, and rejection reason. A failed local mask must not be replaced by an unrecorded global correction.
