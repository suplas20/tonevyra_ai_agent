# Tonevyra AI Agent — AI Coding Agent Rules

Version: v2.0-tonevyra-db-schema
Target agents: Claude Code, Codex, AI coding agents
Project type: Local AI photo correction agent
Primary language: Python 3.11
Primary DB: PostgreSQL
Primary interface in MVP: CLI first

This file is the highest-level implementation rule set for Tonevyra AI Agent. `skills/*/SKILL.md` files define area-specific procedures. If this file conflicts with any other project note, this file wins.

Legacy project names such as `MW Photo Correction Agent`, `mw_photo_agent`, or `mw-agent` may appear in old documents. New implementation must use the Tonevyra naming policy below unless an existing file is being migrated.

---

## 1. Product Definition

Tonevyra AI Agent is a local, offline-first photo correction automation agent.

Official naming:

```text
Product name: Tonevyra AI
Korean reading: 톤바이라 AI
Full technical name: Tonevyra AI Agent
Category description: Local AI Photo Correction Agent
```

Tonevyra AI is not a general chatbot, not a dashboard-first app, and not a blog/Instagram/homepage automation system.

The MVP flow is:

```text
Input folder
→ file detection
→ file stabilization
→ PostgreSQL task registration
→ 1024px sRGB JPEG preview generation
→ vision model analysis
→ correction planning
→ Lightroom Classic JSON bridge
→ Lightroom export
→ quality gate
→ PASS / REVIEW_REQUIRED / FAILED
→ persistence + artifact storage + crash recovery
```

---

## 2. Canonical Naming Policy

Use these names for new implementation:

```text
Repository / project folder: tonevyra_agent
Python package: tonevyra_agent
CLI command: tonevyra-agent
PostgreSQL database: tonevyra_agent
PostgreSQL app role: tonevyra_app
Lightroom plugin folder: TonevyraAI.lrplugin
Primary DB URL env var: TONEVYRA_DATABASE_URL
```

Do not introduce new `mw_photo_agent`, `MWPhotoAgent`, or `mw-agent` identifiers in new code. If older harness files or documents still use MW naming, treat them as legacy references to be migrated, not as current policy.

Temporary compatibility aliases may be accepted only when migrating old scripts, but canonical documentation, `.env.example`, CLI help, and new source code must use Tonevyra names.

---

## 3. Response Language Policy

User-facing explanations, progress updates, final reports, and implementation summaries must be written in Korean unless the user explicitly asks for another language.

Code identifiers, commands, file paths, logs, database object names, environment variable names, and quoted tool output may remain in their original language.

---

## 4. Non-Negotiable Rules

1. PostgreSQL is the operational database. SQLite is not allowed as the main DB.
2. Heavy payloads, images, previews, exports, raw model responses, prompts, and detailed quality outputs must not be stored as DB blobs.
3. Durable outputs must be stored through `storage/artifacts.py` using atomic write, SHA-256 checksum, and DB artifact registration.
4. The vision model is an analyzer only. It must not directly edit images or bypass the Correction Planner.
5. No user data may leave the machine: original photos, previews, prompts, metadata, raw responses, structured analyses, correction plans, exports, quality results, feedback records, manual edit deltas, and training candidates are all local-only.
6. Runtime model loading must be local-only: `local_files_only=True`, offline env vars, no runtime download, no remote API, no external URL image loading, and no `trust_remote_code=True`.
7. The model worker must be designed so outbound network can be blocked at the OS firewall level.
8. Recovery must use PostgreSQL state + artifact records + artifact file existence + checksums + Lightroom response/export file existence. Logs are not a recovery source.
9. CLI is the only MVP operator interface. React dashboard and FastAPI-first work are deferred.
10. Mock Vision and Fake Lightroom must pass before connecting a real Qwen backend or the real Lightroom Lua plugin.
11. Every feature must include or update at least one unit test, harness test, smoke test, recovery test, or security check.
12. Worker concurrency is 1 in MVP because the GPU/unified memory budget is shared with Lightroom Classic.
13. Every autonomous behavior must be implemented as an explicit bounded product loop with persisted evidence.
14. Do not create open-ended loops, unbounded retries, hidden background training, external training calls, or model fine-tuning during normal photo processing.
15. If a user request conflicts with these rules, do not implement it. Report the conflict.
16. When uncertain, implement the smallest end-to-end proof that preserves privacy, recoverability, and pipeline correctness.

---

## 4. MVP Scope

### Must build

```text
- Folder watcher
- File stabilization
- PostgreSQL persistence
- Local artifact storage
- 1024px sRGB JPEG preview generation
- EXIF/basic metadata extraction
- VisionModelBackend interface
- MockVisionBackend
- Qwen candidate backend
- Correction Planner
- Lightroom Classic file-based JSON bridge
- Minimal Lightroom Lua plugin PoC
- Fake Lightroom harness
- Quality gate
- CLI commands
- Crash recovery
- Loop event recording
- Feedback data capture
- Learning sample candidate registration
- Testing harness
```

### Must not build in MVP

```text
- Full React dashboard
- FastAPI-first architecture
- Blog automation
- Instagram automation
- Homepage inquiry automation
- General LLM chat
- SaaS account system
- Multi-user collaboration
- Redis
- MinIO
- NATS
- Celery
- Complex worker pool
- Automatic model fine-tuning during normal processing
- External training service
- Silent learning without local user-approved policy
- High-quality 2048px multi-crop model input as default
- Lightroom neutral preview as default
```

---

## 5. Database Bootstrap Policy

Tonevyra AI uses exactly one product database in MVP:

```text
Database: tonevyra_agent
Application role: tonevyra_app
Schema: public
Admin role: postgres
```

`postgres` is for installation, bootstrap, maintenance, database creation, and role creation only. The application runtime must not connect as `postgres`.

The application runtime must connect with:

```env
TONEVYRA_DATABASE_URL=postgresql+psycopg://tonevyra_app:<password>@localhost:5432/tonevyra_agent
```

A local installation may run on each user PC, but the app must still use a dedicated app role. Local-only deployment does not justify using the `postgres` superuser for normal app execution.

Do not create separate databases for stages, artifacts, quality, feedback, or learning. Those are tables inside `tonevyra_agent`.

The default product schema is `public`. Do not introduce extra schemas unless a future migration explicitly justifies it.

---

## 6. Database Schema Policy

The MVP database contract includes these objects:

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
- pgcrypto, for gen_random_uuid()
- public.set_updated_at(), for updated_at triggers
```

`image_tasks` is the source of truth for task status and current stage.

`task_artifacts` indexes durable local artifact files. It must store path, checksum, size, type, and version. It must not store binary image payloads.

`task_events` records state transitions, loop events, recovery events, failure events, and human review events. Loop activity is an event, not a task status.

`stage_results` stores stage-level summaries and timing. It must not store huge raw model outputs or debug logs.

`quality_results` stores the quality gate result:

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
```

`feedback_records` stores local user feedback and manual edit comparison data.

`learning_samples` stores local candidate records for planner calibration, style profile, camera profile, and future offline model fine-tune candidates. MVP must not perform direct model fine-tuning during normal processing.

`v_task_summary` is a read-only convenience view. It may appear under Views in DBeaver, not Tables.

---

## 7. Migration Policy

Manual SQL created through DBeaver is allowed only for initial local bootstrap and verification.

After implementation begins, schema changes must be managed through Alembic migrations. Do not keep manually editing tables in DBeaver.

Required rules:

```text
- SQLAlchemy models must match the live PostgreSQL schema.
- Alembic migrations must be the source of truth for future schema changes.
- New status, stage, error_code, artifact_type, and decision values must be added through code enums and migrations together.
- DBeaver may be used for inspection and ad-hoc verification, not for untracked schema edits.
- Migration scripts must not create SQLite alternatives.
- Migration scripts must not store image binaries as DB blobs.
```

If the existing local database was bootstrapped manually, the first Alembic baseline must match that schema exactly before adding new changes.

---

## 8. MVP Model Input Policy

The MVP model input is:

```text
1024px sRGB JPEG preview
+ EXIF/basic metadata
```

The model must not receive the original RAW file directly.

Correct interpretation:

```text
The original RAW/JPG is still used for:
- metadata extraction
- Lightroom correction target
- export generation
- quality comparison

The model receives:
- generated preview image
- basic metadata
```

Deferred improvements:

```text
- 1536px/2048px high-quality preview
- subject crop
- center crop
- multi-view model input
- Lightroom neutral preview
- Qwen 7B/8B as default
```

These are not part of MVP default behavior.

---

## 9. Model Role Rule

The vision model is an analyzer, not the final editor.

The model may determine:

```text
- scene_type
- main_subject
- usability
- exposure issue
- color cast
- haze/turbidity
- contrast issue
- sharpness issue
- noise issue
- risk flags
- confidence
```

The model must not directly control final Lightroom correction without validation.

Correct flow:

```text
Vision Model
→ structured analysis
→ Correction Planner
→ clamped Lightroom adjustment plan
→ Lightroom Bridge
```

Wrong flow:

```text
Vision Model
→ raw Lightroom values
→ directly applied without validation
```

---

## 10. Qwen and Model Backend Policy

Qwen is allowed only as a local, replaceable model candidate.

Qwen must not be treated as a hard dependency.

The system must be model-backend replaceable:

```text
VisionModelBackend
  ├─ MockVisionBackend
  ├─ QwenVisionBackend
  └─ FutureAlternativeVisionBackend
```

No project code may assume Qwen is the only supported model.

Stable MVP default after mock pipeline:

```text
Qwen2.5-VL-3B 4bit
```

Validation candidate:

```text
Qwen3-VL-4B 4bit
```

Quality profile, not MVP default:

```text
Qwen2.5-VL-7B 4bit
Qwen3-VL-8B 4bit
```

Validation candidates must pass benchmark with Lightroom Classic running before becoming default.

---

## 11. Local Model Security Requirements

Required runtime behavior:

```text
- Use local model files only.
- Use local_files_only=True.
- Do not use trust_remote_code=True.
- Do not download model files during photo processing.
- Do not call remote APIs.
- Do not load images from external URLs.
- Prefer safetensors or verified GGUF files.
- Avoid pickle-based model files when possible.
- Pin model revision/version.
- Store model files under models/ or configured local model root.
- Record model file hash/checksum.
- Disable Hugging Face / hub online behavior at runtime.
- Disable telemetry where possible.
- Keep model worker network-blockable at OS firewall level.
```

Recommended runtime env vars:

```bash
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
```

Environment variables are helpful but not sufficient. The model worker must still be isolated and network-blockable.

---

## 12. Required Python Structure

Use the simple MVP structure below. Do not over-engineer early.

```text
tonevyra_agent/
  pyproject.toml
  README.md
  .env.example
  AGENTS.md
  CLAUDE.md
  skills/

  src/tonevyra_agent/
    __init__.py
    main.py
    cli.py

    core/
      config.py
      enums.py
      errors.py

    agent/
      runner.py
      watcher.py
      worker.py
      recovery.py
      loops.py

    db/
      database.py
      models.py
      repositories.py

    storage/
      artifacts.py

    images/
      metadata.py
      preview.py

    vision/
      analyzer.py
      model.py
      schemas.py

    correction/
      planner.py
      schemas.py

    lightroom/
      bridge.py
      schemas.py
      plugin/TonevyraAI.lrplugin/
        Info.lua
        Main.lua

    quality/
      analyzer.py
      scoring.py
      schemas.py

    learning/
      feedback.py
      dataset_builder.py
      calibration.py
      schemas.py

  harness/
    fixtures/
    fake_lightroom/
    scripts/

  tests/

  runtime/
    input/
    output/
      temp/
      pass/
      review_required/
      failed/
    artifacts/
    previews/
    bridge/
      requests/
      processing/
      responses/
      errors/

  logs/
  models/
```

---

## 13. Layer Responsibility Rule

```text
cli.py:
  User command entry point.

main.py:
  App startup entry point.

agent/:
  Orchestrates the photo processing pipeline and explicit product loops.

images/:
  Extracts metadata and creates preview images.

vision/:
  Runs model analysis and validates model output.

correction/:
  Converts model analysis into Lightroom adjustment plans.

lightroom/:
  Handles Python ↔ Lightroom Classic JSON bridge.

quality/:
  Evaluates exported images and returns quality decision.

learning/:
  Captures feedback, builds local learning samples, and calibrates planner rules later.

db/:
  Handles PostgreSQL models and repository operations.

storage/:
  Handles artifact save/load/checksum/atomic write.

core/:
  Shared config, enums, and errors.
```

---

## 14. Dependency Direction Rule

Allowed:

```text
cli/main
→ agent
→ images / vision / correction / lightroom / quality / learning
→ db / storage / core
```

Forbidden:

```text
db → agent
storage → vision
vision → lightroom
correction → model loading
quality → lightroom request
lightroom → vision
learning → lightroom direct catalog editing
cli → raw SQL
anything → cli
```

`agent/worker.py` orchestrates the pipeline. Individual modules must not orchestrate the whole system.

---

## 15. State Machine

Allowed task statuses:

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

Terminal statuses:

```text
PASS
REVIEW_REQUIRED
FAILED
SKIPPED
```

Do not invent new status strings. Status values must live in `core/enums.py` and must match database CHECK constraints.

Allowed stages:

```text
watch
metadata
preview
vision
correction_plan
lightroom
export
quality
feedback
recovery
```

Loop events are not task statuses. Store loop activity in `task_events`.

---

## 16. Artifact + Database Commit Order

Filesystem writes are not part of PostgreSQL transactions. Use this sequence:

```text
1. Write artifact to a temp file in the same directory.
2. Flush and fsync when possible.
3. Atomic rename temp file to final artifact path.
4. Calculate SHA-256 checksum and size.
5. Start DB transaction.
6. Register/update task_artifacts row.
7. Insert/update stage summary row.
8. Update image_tasks status/current_stage/summary fields.
9. Insert task_event.
10. Commit.
```

Do not mark a stage complete before its required artifacts are durably written and registered.

---

## 17. Artifact Storage Rule

Artifact Storage is mandatory.

Use local file-based artifact storage in MVP.

Artifact root:

```text
runtime/artifacts/
```

Expected per-task artifacts:

```text
exif.json
preview.jpg
vision_prompt.txt
vision_raw_response.json
vision_structured.json
correction_plan.json
lightroom_request.json
lightroom_response.json
quality_detail.json
recovery_decision.json
retry_history.json
ai_settings.json
final_settings.json
manual_edit_delta.json
user_feedback.json
feedback_record.json
training_sample_manifest.json
```

PostgreSQL stores artifact metadata:

```text
task_id
artifact_type
artifact_path
size_bytes
sha256
mime_type
version
created_at
```

Artifact files are not debug logs. They are durable processing outputs.

---

## 18. Lightroom Bridge Policy

MVP Lightroom integration uses Lightroom Classic Lua plugin + file-based JSON bridge.

```text
Python Agent
→ runtime/bridge/requests/*.json
→ Lightroom Classic Lua Plugin
→ runtime/bridge/processing/*.json
→ Lightroom Classic export
→ runtime/bridge/responses/*.json
→ Python Agent
```

Forbidden:

```text
- Lightroom Cloud API in MVP
- UI-click automation
- Python direct catalog-file editing
```

Request JSON sent to Lightroom must use normalized absolute paths for `source_path` and `export_path`. The DB may store relative artifact paths, but the Lua plugin payload must not depend on the process working directory.

The Lua plugin must not run AI models, access PostgreSQL, perform quality scoring, manage the full task pipeline, or make correction decisions.

---

## 19. Folder Watcher Policy

Supported input extensions are configurable. Initial defaults:

```text
.cr3 .cr2 .nef .arw .dng .jpg .jpeg
```

Ignored files must be silently ignored and must not create SKIPPED tasks:

```text
hidden files
.tmp
.part
.crdownload
.xmp
.DS_Store
files starting with ._
```

Unsupported visible files may create SKIPPED tasks with `UNSUPPORTED_FILE_TYPE` when useful for operator visibility.

---

## 20. Quality Gate Policy

Quality gate evaluates the exported image and returns:

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
```

Initial configurable thresholds:

```text
PASS: overall_score >= 85
REVIEW_REQUIRED: 70 <= overall_score < 85
FAILED: overall_score < 70
```

Planner `requires_review=true`, severe clamp, export failure, or safety overrides may force REVIEW_REQUIRED or FAILED.

---

## 21. Loop Engineering Policy

Loop engineering means the finished product agent's automatic work-loop design. It does not mean the software development process.

Required MVP product loops:

```text
- Watch Loop
- Processing Loop
- Quality Loop
- Recovery Loop
- Feedback Loop
- Model Benchmark Loop
```

Every autonomous product loop must define:

```text
loop name
entry condition
allowed actions
state transitions
retry limit
timeout
exit condition
failure condition
human review condition
persisted evidence
harness verification
```

Every repeated action must have a bounded retry count or a safe terminal state.

Valid loop outcomes:

```text
continue to next valid stage
PASS
REVIEW_REQUIRED
FAILED
SKIPPED
retry within limit
human review required
```

If no safe next action exists, use REVIEW_REQUIRED or FAILED with a structured error code.

---

## 22. Feedback Learning Policy

MVP may collect local learning-ready data only. It must not train or fine-tune the vision model during normal photo processing.

Collectable local data:

```text
user_action
rating
reason_tags
ai_settings_json
final_settings_json
manual_edit_delta_json
accepted
scene_type
camera/lens metadata
model backend/version
correction planner version
quality result
```

Learning target order:

```text
1. Data collection only
2. Correction Planner calibration
3. User style profile
4. Camera/lens/scene profile
5. Offline model fine-tuning after enough approved data exists
```

Future model fine-tuning must be offline, opt-in, versioned, benchmarked, reversible, and separate from normal processing. No external training service or data transmission is allowed.

Manual Lightroom edit detection must compare AI-applied Develop Settings with final user-reviewed Develop Settings via plugin-readable settings snapshots. Python must not read or modify Lightroom catalog files directly.

---

## 23. CLI Commands

Required MVP CLI commands:

```bash
tonevyra-agent init
tonevyra-agent doctor
tonevyra-agent start
tonevyra-agent stop
tonevyra-agent status
tonevyra-agent tasks --status X
tonevyra-agent task TASK_ID
tonevyra-agent scan
tonevyra-agent retry TASK_ID
tonevyra-agent process FILE_PATH
tonevyra-agent test-lightroom
tonevyra-agent test-vision
```

CLI must not contain business logic, raw SQL, direct artifact writes, or direct model loading.

Legacy `mw-agent` commands may be supported temporarily as aliases only during migration.

---

## 24. Recovery Policy

On startup:

```text
1. Load unfinished tasks from PostgreSQL.
2. Check task status and current stage.
3. Check artifact records.
4. Verify artifact file existence and checksum.
5. Check Lightroom response files.
6. Check export files.
7. Resume from the safest valid stage.
```

Examples:

```text
ANALYZING + vision_structured artifact exists → resume from correction planning
LIGHTROOM_REQUESTED + response exists → process Lightroom response
EXPORT_DONE + export exists → resume from quality check
PASS but export file missing → mark FAILED or schedule re-export
```

Recovery must never rely on logs as the source of truth.

---

## 25. Error Handling Policy

Use structured error codes. Do not rely only on free-text messages.

Allowed initial error codes:

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

Each failed task must store:

```text
error_code
error_message
failed_stage
retry_count
updated_at
```

Error codes must live in `core/errors.py` or `core/enums.py` and must match database CHECK constraints.

---

## 26. Testing and Harness Policy

Harness must verify behavior before real model and real Lightroom integration.

Required checks:

```text
- DB connectivity through TONEVYRA_DATABASE_URL
- required tables exist in tonevyra_agent.public
- no app runtime uses postgres superuser
- artifact files exist for DB artifact rows
- checksums match when available
- final statuses are controlled values
- recovery can resume unfinished tasks
- mock vision pipeline passes before Qwen backend
- fake Lightroom pipeline passes before real Lua plugin
- local-only/security check passes
```

If old harness scripts still expect `MW_*` env vars, migrate them to `TONEVYRA_*` or support compatibility aliases while keeping Tonevyra names as primary.

---

## 27. MVP Simplicity Rule

Do not over-engineer.

For MVP, avoid:

```text
services/ layer
dependency injection container
unit_of_work.py
FastAPI app
React dashboard
model backend folder explosion
complex event bus
message broker
Redis
MinIO
Celery
Kubernetes
microservices
```

Add these only after the MVP pipeline is working and code size requires separation.

---

## 28. Development Order

Implement in this order:

```text
1. Project skeleton using Tonevyra naming
2. core config/enums/errors
3. PostgreSQL SQLAlchemy models matching existing schema
4. Alembic baseline/migration setup
5. DB repositories
6. Artifact storage
7. Folder watcher
8. Preview generation
9. Mock vision model
10. Correction planner
11. Lightroom JSON bridge
12. Minimal Lua plugin PoC
13. Quality gate
14. Agent worker pipeline
15. CLI commands
16. Crash recovery
17. Feedback data capture
18. Loop event recording
19. Qwen local backend
20. Model benchmark loop
21. Quality testing
22. Dashboard later
```

Do not attach Qwen before the mock model pipeline works.

---

## 29. Definition of MVP Done

MVP is done when:

```text
1. A photo placed in runtime/input is detected.
2. The file is stabilized.
3. A task is created in PostgreSQL tonevyra_agent.image_tasks.
4. A 1024px preview is generated.
5. Mock or Qwen vision analysis returns structured JSON.
6. Artifacts are saved atomically and indexed in task_artifacts.
7. Correction planner creates Lightroom adjustment JSON.
8. Lightroom request JSON is written.
9. Lightroom plugin or fake worker exports a corrected image.
10. Quality gate evaluates the exported image.
11. Result is classified as PASS / REVIEW_REQUIRED / FAILED.
12. PostgreSQL stores final task status.
13. Crash recovery can resume unfinished tasks.
14. Loop events are recorded in task_events.
15. Feedback data structure exists and can capture local user review data.
16. The process works without React dashboard.
```

---

## 30. Final Priority

When in doubt, follow this priority:

```text
1. Data privacy
2. Local-only execution
3. Recoverability
4. Database contract correctness
5. Artifact integrity
6. End-to-end photo pipeline
7. Lightroom bridge correctness
8. Quality validation
9. Loop safety and bounded retry
10. Feedback learning data integrity
11. Simplicity
12. Performance
13. UI
```

The goal is not to create a beautiful dashboard first.

The goal is to create a local, secure, recoverable photo correction agent that can process real photos through Lightroom Classic and produce classified output.
