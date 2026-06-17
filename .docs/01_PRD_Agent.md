# Tonevyra AI PRD - ?쒗뭹 ?붽뎄?ы빆

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

## 1. MVP Goal

Tonevyra AI is a local AI photo correction agent. The MVP must process photos end-to-end without a React dashboard.

Primary MVP flow:

```text
Input Folder
-> File Detection
-> File Stabilization
-> image_tasks registration
-> Preview Generation
-> Vision Analysis
-> Correction Planning
-> Lightroom Bridge
-> Export
-> Quality Gate
-> PASS / REVIEW_REQUIRED / FAILED
-> Persistence + Artifact Storage
```

## 2. Must Build

```text
folder watcher
file stabilization
PostgreSQL persistence against tonevyra_agent
actionable SQLAlchemy repositories
local artifact storage
1024px sRGB JPEG preview generation
mock vision backend
replaceable Qwen backend interface
correction planner
Lightroom JSON bridge
fake Lightroom backend
quality gate
CLI commands
crash recovery
feedback data storage foundation
```

## 3. Must Not Build in MVP

```text
React dashboard
FastAPI-first backend
blog/Instagram/homepage automation
general chatbot
SaaS/multi-user account system
Redis / Celery / MinIO / NATS / Kubernetes
complex worker pool
automatic model fine-tuning during normal processing
external training service
```

## 4. Model Input Policy

The model receives only:

```text
1024px sRGB JPEG preview
EXIF/basic metadata
```

The original RAW/JPG remains the Lightroom correction target and export source, but it must not be passed directly to the model.

## 5. Acceptance Criteria

The MVP is accepted when:

```text
- one supported photo placed in runtime/input is detected
- task is created in tonevyra_agent.public.image_tasks
- artifacts are written atomically and registered in task_artifacts
- Mock Vision returns structured analysis
- Correction Planner creates clamped Lightroom plan
- Fake Lightroom exports a file
- Quality Gate stores quality_results
- task ends in PASS / REVIEW_REQUIRED / FAILED / SKIPPED
- Recovery can resume unfinished task states
- CLI can run doctor/status/retry-related operations
```

## 6. Product Naming Policy

Use Tonevyra AI for product-facing language.

Implementation naming:

```text
Python package: tonevyra_agent
CLI: tonevyra-agent
Database: tonevyra_agent
DB app role: tonevyra_app
Lightroom plugin folder: TonevyraAI.lrplugin
```

Do not continue using `mw_photo_agent` or `mw-agent` in new implementation code unless compatibility wrappers are explicitly requested.
