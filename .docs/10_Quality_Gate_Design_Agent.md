# Tonevyra AI - Quality Gate Design

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

Quality Gate evaluates the exported image and classifies the final decision.

## 2. Scores

```text
exposure_score
color_score
sharpness_score
noise_score
saturation_score
underwater_cast_score
overall_score
```

## 3. Thresholds

Initial configurable thresholds:

```text
PASS: overall_score >= 85
REVIEW_REQUIRED: 70 <= overall_score < 85
FAILED: overall_score < 70
```

## 4. Storage

```text
quality_detail.json -> Artifact Storage
quality_results -> PostgreSQL summary
image_tasks.overall_score / quality_decision -> quick lookup
```

## 5. Quality Loop

```text
inspect exported image
-> calculate scores
-> write quality_detail.json
-> insert quality_results
-> update image_tasks
-> record task_events
-> stop at PASS / REVIEW_REQUIRED / FAILED
```

## 6. Retry Policy

MVP default is one-pass quality decision. Automatic re-correction is deferred. If added later, retry limits must be explicit and loop evidence must be recorded.

Quality decisions become feedback learning signals when the user confirms or overrides them.

---

## T-029 Local Mask Quality Addendum

Post-export evaluation for a local mask must assess both target improvement and collateral damage.

```text
target_color_recovery_gain
background_color_spill
neutral_or_skin_shift
highlight_clipping_delta
mask_alignment
mask_boundary_visibility
local_adjustment_naturalness
```

Plugin `status=applied` is technical evidence only. The Agent remains responsible for `APPROVED`, retry, review, or failure decisions.
