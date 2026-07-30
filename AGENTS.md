# Tonevyra AI Agent — AI Coding Agent Rules

Version: v2.3-tonevyra-t032-planner-api-separation
Target agents: Claude Code, Codex, AI coding agents
Project type: Local-first AI photo correction agent with a separated Planner API
Primary language: Python 3.11
Primary DB: PostgreSQL
Primary interfaces in MVP: CLI + thin Windows system tray / macOS menu bar shells

This file is the highest-level implementation rule set for Tonevyra AI Agent. `skills/*/SKILL.md` files define area-specific procedures. If this file conflicts with any other project note, this file wins.

Legacy project names such as `MW Photo Correction Agent`, `mw_photo_agent`, or `mw-agent` may appear in old documents. New implementation must use the Tonevyra naming policy below unless an existing file is being migrated.

---

## 1. Product Definition

Tonevyra AI Agent is a local-first photo correction automation agent. Original photos, previews, the vision model, Lightroom execution, exports, and quality evaluation remain local. T-032 introduces one explicitly approved remote component: the code-based Correction Planner Service.

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
5. Original photos, previews, prompts, raw model responses, exports, quality results, feedback records, manual edit deltas, training candidates, local paths, GPS, and device/customer identity remain local-only. T-032 permits only a privacy-scrubbed, allowlisted structured analysis request to the approved Planner API; see Section 35.
6. Runtime model loading remains local-only: `local_files_only=True`, offline env vars, no model API, no runtime download, no external URL image loading, and no `trust_remote_code=True`. The inference Worker must not hold Planner API credentials or perform network calls.
7. The model Worker must be designed so outbound network can be blocked at the OS firewall level. Only the separate Planner API client component may access the exact allowlisted Planner host.
8. Recovery must use PostgreSQL state + artifact records + artifact file existence + checksums + Lightroom response/export file existence. Logs are not a recovery source.
9. CLI remains the diagnostic/operator interface. T-030 authorizes a thin Windows system tray shell and T-031 adds a thin macOS menu bar shell. Status surfaces expose only allowlisted commands and must not own business logic. React dashboard and a FastAPI-first rewrite of the local Agent remain deferred; T-032 authorizes a dedicated FastAPI Planner Service only.
10. Mock Vision and Fake Lightroom must pass before connecting a real Qwen backend or the real Lightroom Lua plugin.
11. Every feature must include or update at least one unit test, harness test, smoke test, recovery test, or security check.
12. Main model and Lightroom worker concurrency is 1 in MVP because GPU/unified memory is shared with Lightroom Classic. The inference model must be lazy-loaded in a separate Worker and unloaded by terminating that Worker after bounded idle grace unless the user explicitly enables keep-warm mode. Bounded parallel file-stability probes are allowed only when they cannot start duplicate processing.
13. Every autonomous behavior must be implemented as an explicit bounded product loop with persisted evidence.
14. Do not create open-ended loops, unbounded retries, hidden background training, external training calls, or model fine-tuning during normal photo processing.
15. If a user request conflicts with these rules, do not implement it. Report the conflict.
16. When uncertain, implement the smallest end-to-end proof that preserves privacy, recoverability, and pipeline correctness.

---

## 4. MVP Scope

### Must build

```text
- Windows per-user background Agent
- Windows system tray shell
- macOS Apple Silicon per-user background Agent
- macOS menu bar shell
- Lazy inference Worker with bounded idle GPU-memory release
- Optional current-user autostart
- Folder watcher
- File stabilization
- PostgreSQL persistence
- Local artifact storage
- 1024px sRGB JPEG preview generation
- EXIF/basic metadata extraction
- VisionModelBackend interface
- MockVisionBackend
- Qwen candidate backend
- Planner API client and independent CorrectionPlan validator
- Separate authenticated Correction Planner Service
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
- FastAPI-first rewrite of the local Agent (the dedicated T-032 Planner Service is allowed)
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

Technical stable candidate after mock pipeline:

```text
Qwen2.5-VL-3B 4bit
```

Commercial/default candidate:

```text
Qwen3-VL-4B 4bit
```

Qwen2.5-VL-3B is a technical stable candidate and must not be treated as the commercial default unless a separate license review explicitly approves it.

Qwen3-VL-4B is the commercial/default candidate, but promotion to a default runtime backend still requires explicit local benchmark evidence, license review, rollback documentation, and human approval. No code may silently promote it.

Quality profile, not MVP default:

```text
Qwen2.5-VL-7B 4bit
Qwen3-VL-8B 4bit
```

Commercial/default candidates must pass benchmark with Lightroom Classic running before becoming default.

---

## 11. Local Model Security Requirements

Required runtime behavior:

```text
- Use local model files only.
- Use local_files_only=True.
- Do not use trust_remote_code=True.
- Do not download model files during photo processing.
- The model/inference Worker must not call remote APIs.
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


---

## 31. T-020 Lightroom Final Export Adapter Policy

T-019 applies Agent-created correction values to a Lightroom catalog photo. T-020 automatically exports that corrected rendition to an actual file.

Canonical T-020 flow:

```text
T-019 apply result: status=applied
→ Agent validates apply success
→ Agent writes Lightroom export request
→ Lightroom Plugin automatically exports corrected rendition
→ Plugin writes export result
→ Agent verifies result and actual output file
→ EXPORT_DONE
→ QUALITY_CHECK
```

Canonical paths:

```text
Export requests: runtime/bridge/lightroom_export_requests/
Export results: runtime/bridge/lightroom_export_results/
Temporary corrected output: runtime/output/temp/
```

T-020 rules:

1. Export requests may be created only after a valid T-019 apply result proves that Develop settings were applied.
2. Request `source_path` and `export_path` must be normalized absolute paths.
3. The default MVP export profile is JPEG, quality 95, sRGB, no resize, no source overwrite.
4. Plugin-side automatic bridge processing is the product path. Manual export or selected-photo export is diagnostic only.
5. The Plugin must not analyze photos, generate correction plans, calculate quality scores, access PostgreSQL, or orchestrate the full task.
6. A JSON result with `status=exported` is insufficient by itself. The expected output file must exist, be non-empty, and differ from the source path.
7. `EXPORT_DONE` may be persisted only after result and file verification and artifact registration.
8. Every claimed export request must produce a durable `exported` or `failed` result.
9. Export timeout, retry, duplicate handling, and recovery must be bounded and evidence-based.
10. T-020 must preserve the completed T-019 Apply Adapter behavior and its harness/skills/documents.
11. Do not add new task statuses for T-020. Use `LIGHTROOM_PROCESSING → EXPORT_DONE → QUALITY_CHECK`.
12. Use existing error codes first: `LIGHTROOM_REQUEST_FAILED`, `LIGHTROOM_RESPONSE_TIMEOUT`, `LIGHTROOM_EXPORT_FAILED`, `EXPORT_FILE_MISSING`, `ARTIFACT_WRITE_FAILED`, `DB_WRITE_FAILED`.
13. New error codes require synchronized rule, enum, database constraint, migration, recovery, fixture, and test updates.

Required T-020 references:

```text
.docs/t020/T-020_Lightroom_Final_Export_Adapter_Work_Order.md
skills/lightroom-final-export-adapter/SKILL.md
harness/CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md
harness/scripts/verify_lightroom_export_adapter.py
```

---

## 32. T-021 Dual-Mode Agent Core and Closed-Loop Quality Policy

T-021 introduces one Common Agent Core with replaceable analysis and quality providers. It does not authorize separate free and paid agent codebases.

Canonical architecture:

```text
Common Agent Core
→ AnalysisProvider: module | model
→ normalized analysis schema
→ Adjustment Planner + safety clamp
→ T-019 Lightroom Apply Adapter
→ T-020 Lightroom Final Export Adapter
→ QualityProvider: module | model
→ Quality Evaluator
→ bounded Retry Controller
→ terminal decision
```

### 32.1 Required responsibility boundaries

1. Provider output is analysis or quality evidence.
2. Adjustment Planner is the only component that creates final bounded Lightroom adjustment values.
3. Lightroom Plugin is a technical execution adapter only.
4. State Manager owns legal transitions.
5. Retry Controller owns retry budget and progress checks.
6. SaaS Plan Policy chooses Provider and retry limits.
7. Model Provider must never bypass Planner, state policy, or quality policy.

Forbidden Provider fields:

```text
lightroom_adjustments
develop_settings
preset_path
final_decision
```

### 32.2 Provider and plan policy

```text
free     → module analysis / module quality / max quality retry 1
lite     → module analysis / module quality / max quality retry 2
standard → model analysis / model quality / max quality retry 2
pro      → model analysis / model quality / max quality retry 3
t021_mvp → module analysis / module quality / max quality retry 2
```

Do not deliberately degrade Module Provider output for lower plans. Plan differentiation must come from provider capability, throughput, retry depth, output features, and advanced semantics.

Model Provider remains local-only. No remote API fallback, runtime download, external URL image loading, or silent Module fallback is allowed.

### 32.3 T-021 state machine

```text
CREATED
→ ANALYZING
→ ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
→ EXPORTED
→ EVALUATING
→ APPROVED
```

Retry:

```text
EVALUATING
→ RETRY_REQUIRED
→ ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
→ EXPORTED
→ EVALUATING
```

Terminal classifications:

```text
APPROVED
SOURCE_LIMITED
TECHNICAL_FAILED
FINAL_FAILED
```

`RETRY_REQUIRED` is non-terminal and must always be bounded by plan policy.

### 32.4 Export and quality boundary

`EXPORTED` may be entered only after all T-020 evidence is valid:

```text
status=exported
expected output exists
output size > 0
source path differs from export path
artifact checksum and DB registration succeed
```

The Plugin must not calculate quality scores or set `APPROVED`, `RETRY_REQUIRED`, `SOURCE_LIMITED`, or `FINAL_FAILED`.

### 32.5 Failure separation

```text
TECHNICAL_FAILED: provider, schema, Lightroom, Plugin, bridge, file, artifact, DB, timeout, or state error
RETRY_REQUIRED: quality below target but an actionable strategy remains
SOURCE_LIMITED: durable evidence that source data cannot be recovered by correction
FINAL_FAILED: retry budget exhausted, no progress, or policy stop
APPROVED: technical and quality gates pass
```

Technical recovery attempts and quality retries use separate bounded budgets.

### 32.6 Attempt and artifact policy

Every retry creates a new immutable attempt:

```text
job_id remains stable
attempt_id is new
attempt_no increments
apply/export request ids are new
previous artifacts remain unchanged
plan delta and score delta are recorded
```

Required attempt artifacts:

```text
attempt_manifest.json
analysis_result.json
normalized_analysis.json
adjustment_plan.json
lightroom_apply_request.json
lightroom_apply_result.json
lightroom_export_request.json
lightroom_export_result.json
quality_evaluation.json
state_transition.json
retry_decision.json when applicable
```

### 32.7 Legacy compatibility

Do not delete legacy status values or rewrite historical rows during T-021 migration.

Before the additive DB migration is active, use:

```text
EXPORTED → EXPORT_DONE + T-021 event evidence
EVALUATING → QUALITY_CHECK + T-021 event evidence
APPROVED → PASS + t021_decision
SOURCE_LIMITED / TECHNICAL_FAILED / FINAL_FAILED → FAILED + failure_class
RETRY_REQUIRED → non-terminal task event
```

Any status/enum expansion requires synchronized code enum, DB constraint, Alembic migration, repository, recovery, CLI, fixture, and harness updates.

### 32.8 Mandatory regression and acceptance gates

The completed T-019 and T-020 contracts remain mandatory. T-021 cannot pass if their files or behavior are removed.

Required references:

```text
.docs/t021/T-021_Dual_Mode_Photo_Agent_Core_Work_Order.md
.docs/t021/T-021_Implementation_Specification.md
skills/dual-mode-agent-core/SKILL.md
skills/closed-loop-quality-reprocessing/SKILL.md
harness/CONTRACT_T021_DUAL_MODE_CLOSED_LOOP.md
harness/scripts/verify_t021_dual_mode_closed_loop.py
```

The T-020 baseline contains 25 skills. T-021 must preserve all 25 and add the two T-021 skills for a cumulative total of 27.


---

## 33. T-029 Lightroom Native Mask and Radial Fallback Policy

### 33.0 Scope update: radial fallback excluded

As of 2026-06-29, radial-gradient / radial-template fallback is excluded from T-029.

This update overrides any older T-029 text in this repository that says `radial_template` is a valid automatic fallback. T-029 now allows native Lightroom mask execution only when the intended target is actually detected by supported native mask types. If Subject, People, Object, Sky, or Background does not identify the intended target, the Planner must choose `skip_local` or `review_required`; it must not create a radial substitute, global substitute, brush fallback, generated XMP fallback, or UI automation path.

Allowed T-029 strategies:

```text
native_ai
skip_local
review_required
```

Forbidden T-029 strategies and fields:

```text
radial_template
template_ref
template_path
preset_path
generated_radial_xmp
mouse_coordinates
```

T-029 extends the existing T-019 Apply Adapter and T-023 local-adjustment planning boundary. It does not authorize the model or Lightroom Plugin to choose arbitrary masks or correction values.

Canonical flow:

```text
semantic target evidence
→ Mask Strategy Planner
→ capability + native-detection reliability check
→ native_ai or deterministic radial_template
→ bounded mask apply request
→ Lightroom Plugin technical execution
→ export
→ target/spill quality evaluation
```

### 33.1 Responsibility boundary

1. Analysis Providers may output normalized target geometry, confidence, color-loss evidence, and correction intent only.
2. The Mask Strategy Planner is the only component that selects `native_ai`, `radial_template`, `skip_local`, or `review_required`.
3. The Planner is the only component that selects a radial template ID and creates bounded local Lightroom values.
4. The Plugin validates and executes the approved plan. It must not perform semantic reasoning or quality decisions.
5. Native mask API availability is not proof that the intended target was detected.
6. When Subject, People, and Object fail to detect a small secondary target, the Planner may use radial fallback only when geometry-fit and spill-safety thresholds pass.

Forbidden Provider fields:

```text
plugin_command
preset_path
template_path
lightroom_mask_payload
final_develop_settings
execute_mask
mouse_coordinates
```

### 33.2 Radial template policy

MVP uses a local, versioned, checksum-verified library generated from a human-validated seed radial preset. Runtime arbitrary XMP generation is not authorized.

```text
template ID + library version + expected checksum
→ Plugin local manifest lookup
→ path containment and checksum validation
→ approved Lightroom preset/develop application path
```

The request must not provide an arbitrary preset file path. Template files must not be downloaded at runtime.

### 33.3 Geometry and safety

- Geometry uses EXIF-oriented normalized image coordinates in `0.0..1.0`.
- Template selection must be deterministic for the same target, manifest, policy, and Planner version.
- Persist center distance, coverage, overflow, aspect error, size error, fit score, and acceptance/rejection reason.
- Clamp all local adjustments.
- Preserve user-created masks.
- Plugin-owned masks use `Tonevyra::T029::` names.
- Store pre/post Develop snapshots and perform safe rollback on partial failure.
- Same idempotency key must not create a duplicate mask.
- Do not silently simulate a failed local mask by applying the correction globally.

### 33.4 Prohibited implementation paths

```text
AutoHotkey or pyautogui
screen-coordinate clicking or dragging
Lightroom catalog database modification
runtime overwrite of user sidecar XMP
unverified private Lightroom APIs
brush/object rectangle UI automation
external bitmap-mask injection presented as native Lightroom support
```

### 33.5 Completion evidence

T-029 is not complete until a real Lightroom Classic Phase 0 test proves one pre-authored radial preset can be applied automatically with retained geometry, idempotent replay, user-mask preservation, and safe failure behavior.

Required references:

```text
.docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md
.docs/t029/T-029_Implementation_Specification.md
.docs/t029/T-029_Codex_Prompt.md
.docs/t029/T-029_Lightroom_Live_Test_Checklist.md
.docs/t029/T-029_Seed_Radial_Preset_Preparation_Guide.md
skills/lightroom-radial-mask-execution/SKILL.md
skills/radial-mask-template-library/SKILL.md
harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md
harness/scripts/verify_t029_lightroom_radial_masking.py
harness/scripts/run_t029_radial_masking_runtime.py
```

The T-028 baseline contains 41 `SKILL.md` files. T-029 preserves all 41 and adds two skills for a cumulative total of 43.

## 34. T-030 Windows Background Watcher and System Tray Policy

### 34.1 Runtime boundary

T-030 runs Tonevyra as a Windows per-user background application. It is not a Windows Service.

```text
Tray Shell
→ status rendering + allowlisted commands + Worker supervision

Background Agent Worker
→ watcher + stabilization + PostgreSQL task registration
→ existing processing/recovery/Lightroom pipeline
```

The Tray Shell must never create adjustment plans, execute Lightroom corrections, calculate quality, or write pipeline DB state directly.

### 34.2 Agent runtime states

T-030 adds separate Agent runtime states. They are not `image_tasks.status` values.

```text
STARTING
WATCHING
PROCESSING
PAUSED
DEGRADED
ERROR
STOPPING
STOPPED
```

Do not add new image task statuses for tray or dependency-wait behavior.

### 34.3 Watcher and queue rules

```text
filesystem events
→ debounce/coalescing
→ bounded file-stability gate
→ exclusion and recursion safety
→ transactional PostgreSQL register-or-get-existing
→ existing processing loop
```

Mandatory:

- Created, Modified, Renamed, Moved-In, and bounded rescan are supported.
- A file still changing size or mtime must not enter analysis.
- PostgreSQL remains the durable queue. SQLite queue/fallback is prohibited.
- Duplicate events, restart, rescan, and second launch must not create duplicate external effects.
- Input/output/runtime/cache path recursion is rejected or explicitly excluded.
- T-030 must not overwrite, move, rename, or delete source photos.

### 34.4 Windows lifecycle

- Use a per-user named mutex or equivalent Windows kernel primitive for Tray and Worker single instance.
- A second launch may activate the existing Tray, but must not start another Worker.
- Worker heartbeat/restart is bounded and must detect crash loops.
- Tray remains alive when Worker crashes and exposes recovery/error state.
- Graceful shutdown stops intake, checkpoints safely, flushes evidence, joins Worker, and removes the Tray icon.
- Current-user autostart may be enabled/disabled without administrator rights.

### 34.5 Tray and brand asset

The tray icon uses the approved Tonevyra aperture symbol without the wordmark. Production assets must come from an approved SVG or transparent high-resolution source, not a screenshot crop.

If an approved source asset is absent:

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
```

A temporary icon may support development tests but cannot satisfy production completion.

### 34.6 Prohibited paths

```text
Windows Service for the interactive tray runtime
SQLite operational queue or fallback
unbounded Worker restart
Tray-owned Planner/quality/DB business logic
processing immediately on Created without stability proof
source overwrite/delete/move
recursive ingestion of Tonevyra outputs
AutoHotkey / pyautogui / screen-coordinate automation
external 0.0.0.0 command listener
```

### 34.7 Completion evidence

T-030 requires static harness, implementation runtime evidence, and real Windows live evidence. Reference harness evidence alone is not a completion proof.

Required references:

```text
.docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md
.docs/t030/T-030_Implementation_Specification.md
.docs/t030/T-030_Codex_Prompt.md
.docs/t030/T-030_Windows_Live_Test_Checklist.md
.docs/t030/T-030_Tray_Icon_Asset_Guide.md
skills/windows-background-agent-lifecycle/SKILL.md
skills/system-tray-operations/SKILL.md
skills/folder-watcher/SKILL.md
harness/CONTRACT_T030_WINDOWS_BACKGROUND_TRAY.md
harness/scripts/verify_t030_windows_background_tray.py
harness/scripts/run_t030_background_tray_reference.py
```

The T-029 baseline contains 43 `SKILL.md` files. T-030 preserves all 43 and adds two skills for a cumulative total of 45.

## T-031 Cross-platform and GPU Memory Policy

```text
- Shared business logic must remain platform-neutral.
- Windows and macOS behavior must be isolated behind adapters.
- Apple Silicon arm64 is the first macOS target.
- Shell/Watcher processes must not import or load the model runtime.
- Exactly one inference Worker is allowed.
- The Worker starts lazily and exits after bounded idle grace.
- `torch.cuda.empty_cache()` alone is not unload evidence.
- CPU fallback on macOS must be explicit and disabled by default.
- macOS completion requires real arm64/MPS/FSEvents/Lightroom evidence.
- Windows VRAM completion requires process-level before/loaded/post-unload evidence.
```

## 35. T-032 Planner API Separation Policy

### 35.1 Authorized boundary

T-032 moves production Correction Planner rule execution out of the local Agent and into `tonevyra_planner_service`.

```text
Local only:
photos, previews, Qwen/model runtime, raw prompts/responses, file paths,
PostgreSQL task state, Lightroom, exports, quality, feedback

Approved remote payload:
allowlisted normalized analysis + minimal non-identifying image context

Remote only:
Planner rules, policy tables, Planner execution, Planner version metadata
```

No other remote API is authorized by T-032.

### 35.2 Production client prohibition

The production Agent distribution must not include Planner rule modules, policy tables, hidden local Planner switches, or automatic local fallback. Test-only Fake/Mock Planner implementations must be clearly isolated and impossible to select silently in production.

### 35.3 Contract and integrity

Required endpoint and evidence:

```text
POST /api/v1/plans
Authorization Bearer device/customer-scoped key
X-Request-ID
Idempotency-Key
request/response schema versions
input_digest
plan_digest
planner_version
policy_version
```

The client independently validates schema, request binding, digest, version, allowed fields, and Lightroom ranges before use.

### 35.4 Privacy

The request is built by allowlist projection. The following are forbidden across the boundary:

```text
original/preview image bytes
filename or local path
GPS/location
camera serial
user/customer identity
prompt or raw model response
Lightroom catalog/plugin/preset path
arbitrary command or executable payload
```

### 35.5 Retry/state

Do not add a new `image_tasks.status` for API waiting. While transient retry is pending, remain at `ANALYSIS_DONE` and record attempts/events. Retry is bounded. Authentication, schema, privacy, digest, version, and idempotency conflicts are not blind retry cases. Retry exhaustion must never silently fall back to a local production Planner.

### 35.6 Idempotency

Persist the sanitized request, request ID, input digest, and idempotency key before sending. Same principal/key/digest returns the committed response. Same key with a different digest is `IDEMPOTENCY_CONFLICT`. Restart/replay must not create duplicate Lightroom effects.

### 35.7 Deployment and completion

Reference deployment uses one Uvicorn worker and one Planner execution concurrency on the 1 OCPU/1GB test server. Production is HTTPS-only, non-root, secret-redacted, body/rate limited, and backed by durable idempotency evidence.

Strict completion requires:

```text
implementation runtime evidence
live HTTPS server evidence
production client build scan
3000 sequential request soak
T-019 through T-031 regressions
```

Reference harness output alone is not completion.

### 35.8 Canonical T-032 references

```text
.docs/t032/T-032_Planner_Engine_API_Separation_Work_Order.md
.docs/t032/T-032_Implementation_Specification.md
.docs/t032/T-032_API_Contract.md
.docs/t032/T-032_Server_Deployment_Guide.md
.docs/t032/T-032_Live_Test_Checklist.md
skills/planner-api-contract/SKILL.md
skills/planner-api-client/SKILL.md
skills/planner-api-service/SKILL.md
skills/planner-api-security/SKILL.md
harness/CONTRACT_T032_PLANNER_API_SEPARATION.md
harness/scripts/verify_t032_planner_api_separation.py
```

T-031 baseline skill count is 47. T-032 adds four skills for a required cumulative total of 51.

The phrase `production local Planner fallback is forbidden` is a hard T-032 rule.

## 36. T-033 Cross-platform Installer Packaging Policy

### 36.1 One-click product contract

```text
User action:
installer launch → OS elevation/admin authentication → one Install action

Automatic:
application payload → bundled Python → PostgreSQL download/install → DB Role/Database → Alembic schema → credential storage → Lightroom plugin/PENDING → startup registration → final doctor → launch
```

Normal installation must require zero manual prerequisite steps and zero manual database steps. Do not expose a PostgreSQL wizard, DB credentials, SQL execution, Alembic commands, PATH changes or plugin file copying to the user.

### 36.2 Distribution boundary

```text
Bundled:
Tonevyra application, Python 3.11.9 runtime, reviewed locked dependencies,
DB migrations, Lightroom plugin, license notices

Downloaded during install:
PostgreSQL latest stable GA installer from approved official sources

External/user-managed:
Lightroom Classic, Adobe Creative Cloud, GPU drivers
```

The PostgreSQL installer must not be bundled in any Windows EXE, macOS PKG/DMG, nested archive, cache seed, or offline payload.

### 36.3 Python

Production packages use the bundled Python 3.11.9 runtime only. Do not inspect PATH to choose another Python, mutate PATH, register file associations, install global packages, or download a newer interpreter during install/first launch.

### 36.4 PostgreSQL

```text
channel = latest-stable
prerelease = forbidden
signed metadata = required
official host = required
SHA-256 = required
publisher/package signature = required
existing user clusters = protected
silent major upgrade = forbidden
```

A new upstream stable major version still requires the Tonevyra DB compatibility gate. If that gate is unavailable, stop safely instead of executing an unverified installer.

### 36.5 Database bootstrap and completion

```text
PostgreSQL unattended install
→ service readiness
→ tonevyra_app Role
→ tonevyra_agent DB
→ Alembic upgrade head
→ required object/privilege verification
→ read/write smoke rollback
→ DPAPI/Credential Manager or Keychain
→ Agent/DB doctor
```

Do not report installation success or start the Agent before this gate passes. Existing databases must not be reset during install or repair.

### 36.6 Platform release gates

Windows release artifacts require Authenticode evidence. macOS release artifacts require Developer ID signing, notarization acceptance, stapling and Gatekeeper evidence. Reference harness output is never live release evidence.

### 36.7 Canonical T-033 references

```text
.docs/t033/T-033_Cross_Platform_Installer_Packaging_Work_Order.md
.docs/t033/T-033_Implementation_Specification.md
.docs/t033/T-033_All_In_One_Installer_Orchestration.md
.docs/t033/T-033_Database_Bootstrap_and_Schema_Automation.md
.docs/t033/T-033_Dependency_Distribution_and_License_Policy.md
.docs/t033/T-033_Windows_Installer_Guide.md
.docs/t033/T-033_macOS_Installer_Guide.md
.docs/t033/T-033_Live_Test_Checklist.md
skills/T033_SKILL_INVENTORY.json
harness/CONTRACT_T033_CROSS_PLATFORM_INSTALLER.md
harness/scripts/verify_t033_cross_platform_installer.py
harness/scripts/verify_t033_all_in_one_install.py
```

T-032 baseline skill count is 51. T-033 preserves all 51 and adds seven skills for a cumulative total of 58.
