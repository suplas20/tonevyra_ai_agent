# Tonevyra AI - Folder Watcher & File Pipeline

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

## 1. Watcher Role

Watch `runtime/input` for supported image files and register tasks.

## 2. Supported Initial Extensions

```text
.cr3
.cr2
.nef
.arw
.dng
.jpg
.jpeg
```

## 3. Ignored Files

Ignore silently:

```text
hidden files
.tmp
.part
.crdownload
.xmp
.DS_Store
._* resource files
```

Unsupported visible files may become `SKIPPED` with `UNSUPPORTED_FILE_TYPE` when useful.

## 4. Stabilizer

Before task creation, verify file size remains stable across configured intervals.

On failure, use:

```text
FILE_NOT_STABLE
```

## 5. Duplicate Prevention

Prevent duplicate tasks by:

```text
source_path
source_hash
```

Use the DB unique constraint on `image_tasks(source_path, source_hash)` as the final safety net.

## 6. Watch Loop

```text
observe input folder
-> ignore temp/sidecar files
-> detect supported photo files
-> wait for file stabilization
-> create image_tasks row
-> record task_events row with watch_loop payload
-> continue watching
```

The Watch Loop exits only when the user stops the agent.

## 7. Preview Output

Generate 1024px sRGB JPEG preview for model input and register it as:

```text
PREVIEW_JPEG
```

Do not pass original RAW directly to the model.

## T-030 Continuous Windows Watcher Addendum

T-030 upgrades the watcher from a CLI-started MVP loop to a continuously supervised Windows background runtime.

```text
Created/Modified/Renamed/Moved-In/Rescan
→ path-normalized debounce
→ size + mtime + read-probe stability
→ exclusion/recursion safety
→ PostgreSQL register-or-get-existing
→ existing processing loop
```

Default stability policy:

```text
interval=2 seconds
required stable samples=3
timeout=300 seconds
```

Pause stops new intake and resume performs a bounded rescan. Event storms, restart, and rescan must have exactly-once external effect. Output, cache, runtime, failed, sidecar, and temporary paths are excluded. T-030 does not modify source files.
