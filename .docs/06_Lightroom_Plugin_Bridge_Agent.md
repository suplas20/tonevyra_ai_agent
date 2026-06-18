# Tonevyra AI - Lightroom Plugin Bridge

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


## T-019 Folder-Driven Update

T-019 supersedes any earlier selected-photo or menu-first Lightroom PoC wording. The canonical implementation path is:

```text
F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
```

The Lightroom plugin is a thin apply worker. The product flow is folder-driven:

```text
input folder -> folder watcher -> Tonevyra agent -> apply request JSON -> Lightroom plugin worker -> apply result JSON -> DB/task_events evidence
```

The plugin must not use the current Lightroom selection as the primary task source. Lightroom menu entries are allowed only for status, diagnostics, worker restart, or manual replay of an existing apply request.

## 1. Protocol

Use file-based JSON bridge.

```text
Python Agent
-> runtime/bridge/requests/*.json
-> Lightroom Classic Lua Plugin
-> runtime/bridge/processing/*.json
-> Lightroom export
-> runtime/bridge/responses/*.json
-> Python Agent
```

## 2. Folders

```text
runtime/bridge/requests
runtime/bridge/processing
runtime/bridge/responses
runtime/bridge/errors
```

## 3. Commands

MVP commands:

```text
PING
IMPORT_PHOTO
APPLY_PRESET
APPLY_ADJUSTMENTS_AND_EXPORT
EXPORT_PHOTO
```

Future feedback-sync commands:

```text
READ_DEVELOP_SETTINGS
READ_AI_APPLIED_SETTINGS
SYNC_CURRENT_SETTINGS
```

## 4. Lua Boundaries

Lua plugin may:

```text
poll request JSON
apply Lightroom adjustments
export corrected image
write response JSON
read Lightroom develop settings for feedback sync
```

Lua plugin must not:

```text
run AI models
access PostgreSQL
perform quality scoring
manage the full task pipeline
make correction decisions
```

## 5. Python Boundaries

Python must not directly read or modify Lightroom catalog files.

All Lightroom state access must go through the Lua plugin and JSON bridge.

## 6. Path Rule

Bridge request payloads must use normalized absolute local paths for Lightroom-facing fields:

```text
source_path
export_path
```

DB may store relative artifact paths, but Lua payloads must not depend on working directory.

## 7. Early MVP

Before real Lightroom integration, implement Fake Lightroom backend:

```text
read request JSON
write response JSON
create fake exported image or copy fixture
record lightroom_response artifact
```
