# Tonevyra AI Implementation Work Order - Agent Execution Document

Version: v2.0  
Audience: Codex, Claude Code, AI coding agents, developer  
Product: Tonevyra AI  
Technical product name: Tonevyra AI Agent  
Python package: `tonevyra_agent`  
CLI: `tonevyra-agent`  
Purpose: This document defines the complete implementation order from the first project foundation step to MVP completion, real Lightroom integration, real local Qwen integration, and model benchmark validation.

---

## 0. Absolute Execution Rule

The agent must implement the tickets in order.

```text
T-001 -> T-002 -> T-003 -> ... -> T-018
```

The agent must implement **one ticket only per execution**.

After finishing one ticket, the agent must stop and report to the user.  
The agent must not continue to the next ticket until the user explicitly approves.

```text
One ticket completed -> report -> wait for user approval -> next ticket
```

Do not auto-continue.

---

## 1. Mandatory Reading Order Before Every Ticket

Before implementing any ticket, read these files in this order:

```text
1. AGENTS.md
2. CLAUDE.md
3. .docs/implementation/Tonevyra_AI_Implementation_Readiness_Agent_v2.md
4. .docs/implementation/Tonevyra_AI_Implementation_Work_Order_Agent_v2.md
5. .docs/00_Loop_Engineering_Global_Addendum_Agent.md
6. The specific 00~15 Agent document related to the current ticket
7. Relevant skills/*/SKILL.md files
8. harness/CONTRACT.md when the ticket requires harness validation
```

If any required file is missing, stop and report the missing file. Do not guess.

---

## 2. Global Product Constants

```text
Product name: Tonevyra AI
Technical product name: Tonevyra AI Agent
Python package: tonevyra_agent
CLI command: tonevyra-agent
Database: tonevyra_agent
Database app user: tonevyra_app
Database schema: public
Database env var: TONEVYRA_DATABASE_URL
Primary runtime mode before real integration: mock vision + fake Lightroom
```

---

## 3. Current MVP Database Objects

The current PostgreSQL database already exists.

Required tables:

```text
image_tasks
task_artifacts
task_events
stage_results
quality_results
feedback_records
learning_samples
```

Required view:

```text
v_task_summary
```

The agent must not create, drop, or alter database tables unless a ticket explicitly authorizes a migration.

Runtime database user must be:

```text
tonevyra_app
```

Do not use the `postgres` superuser as the runtime application user.

---

## 4. Fixed Status Values

Only these task statuses are allowed:

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

Forbidden status values:

```text
PROCESSING
DONE
ERROR
COMPLETED
SUCCESS
FINISHED
```

---

## 5. Fixed Stage Names

Only these stage names are allowed:

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

---

## 6. Fixed Error Codes

Only these error codes are allowed:

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

Do not invent new error codes unless a later approved ticket explicitly changes the contract.

---

## 7. Global Forbidden Scope

Do not implement the following unless the current approved ticket explicitly asks for it:

```text
React dashboard
FastAPI-first architecture
SaaS accounts or permissions
Redis
Celery
Worker pool
MinIO/S3
Real Qwen before mock/fake pipeline passes
Real Lightroom before fake Lightroom pipeline passes
Automatic Qwen fine-tuning
External API inference
Online model download at runtime
Blog/Instagram/homepage automation
Payment/licensing system
```

---

## 8. Ticket Execution Protocol

Every ticket must follow this process:

```text
1. Read mandatory documents.
2. Confirm current ticket ID and scope.
3. Inspect existing project files.
4. Implement the current ticket only.
5. Add or update tests/harness checks required for the ticket.
6. Run validation commands.
7. Produce the required report.
8. Stop.
9. Wait for user approval before continuing.
```

The agent must not begin the next ticket after reporting.

---

## 9. Required Completion Report Format

After every ticket, report exactly in this structure:

```text
Ticket ID:
Implemented scope:
Changed files:
Commands run:
Validation result:
Doctor result:
Harness/test result:
DB result:
Out-of-scope items not implemented:
Assumptions:
Blocked items:
Risks or follow-up notes:
Next recommended ticket:
Waiting for user approval:
```

The `Next recommended ticket` may be mentioned, but must not be implemented.

---

## 10. Full Implementation Roadmap

| Ticket | Name | Main Result |
|---|---|---|
| T-001 | Project Foundation + DB Persistence | Python skeleton, config, enums, DB connection, ORM, repositories, doctor |
| T-002 | Artifact Storage Foundation | Atomic artifact writes, checksum, task_artifacts registration |
| T-003 | Folder Watcher + File Stabilization | Input file detection, ignore rules, stabilization, task registration |
| T-004 | Metadata + 1024px Preview | EXIF/basic metadata and 1024px sRGB JPEG preview |
| T-005 | Mock Vision Backend | Fixture-based structured vision analysis |
| T-006 | Correction Planner | Safe clamped Lightroom adjustment plan |
| T-007 | Fake Lightroom Bridge | Fake JSON bridge, response, and fake export |
| T-008 | Quality Gate | Quality scoring and final PASS/REVIEW_REQUIRED/FAILED |
| T-009 | Worker Pipeline Integration | One-photo full mock/fake processing pipeline |
| T-010 | Smoke Pipeline Harness | End-to-end harness validation |
| T-011 | Recovery Loop | Safe resume/fail from incomplete task state |
| T-012 | Loop Event Evidence | Standard loop evidence and verification |
| T-013 | Feedback Storage Foundation | User feedback and manual edit delta storage contract |
| T-014 | CLI Operations Completion | MVP CLI commands and explicit retry/process/status operations |
| T-015 | Security + Offline Harness | Local-only security checks and no-network validation |
| T-016 | Real Lightroom Lua PoC | Real Lightroom Classic JSON bridge proof of concept |
| T-017 | Local Qwen Backend | Local-only Qwen backend with Qwen2.5 technical candidate and Qwen3 commercial/default candidate slots |
| T-018 | Model Benchmark Loop | Qwen2.5 technical stable candidate vs Qwen3 commercial/default candidate comparison and gated promotion evidence |

---

# T-001: Project Foundation + DB Persistence

## Goal

Create the initial Tonevyra AI Python project foundation and connect it to the existing PostgreSQL database.

## Read

```text
.docs/03_Data_Persistence_Architecture_Agent.md
.docs/04_PostgreSQL_Database_Schema_Agent.md
.docs/12_CLI_Operations_Agent.md
skills/python-mvp-structure/SKILL.md
skills/postgresql-persistence/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
pyproject.toml
.env.example
README.md

src/tonevyra_agent/__init__.py
src/tonevyra_agent/main.py
src/tonevyra_agent/cli.py

src/tonevyra_agent/core/config.py
src/tonevyra_agent/core/enums.py
src/tonevyra_agent/core/errors.py

src/tonevyra_agent/db/database.py
src/tonevyra_agent/db/models.py
src/tonevyra_agent/db/repositories.py
```

## Required Behavior

```text
tonevyra-agent doctor
python -m tonevyra_agent.cli doctor
```

Doctor must verify:

```text
Python version
.env loading
runtime directory existence
input/output/artifacts/previews/bridge/logs folders
PostgreSQL connection
current_database() = tonevyra_agent
current_user = tonevyra_app
required tables exist
v_task_summary view exists
```

Add DB smoke test command:

```text
python -m tonevyra_agent.cli db-smoke-test
```

Smoke test must:

```text
create one test image_task row
create one test task_event row
read test task back
delete test task and related test rows
report success/failure
```

## Do Not Implement

```text
Watcher
Preview generation
Mock Vision
Correction Planner
Fake Lightroom
Quality Gate
Recovery Loop
Feedback Sync
Real Qwen
Real Lightroom
FastAPI
React
Redis/Celery
MinIO
```

## Validation

```bash
python -m tonevyra_agent.cli doctor
python -m tonevyra_agent.cli db-smoke-test
```

## Stop Rule

After T-001 is complete, stop and wait for user approval before T-002.

---

# T-002: Artifact Storage Foundation

## Goal

Implement durable local Artifact Storage with atomic writes, checksum calculation, and PostgreSQL task_artifacts registration.

## Read

```text
.docs/05_Artifact_Storage_Specification_Agent.md
.docs/03_Data_Persistence_Architecture_Agent.md
.docs/07_Agent_Core_State_Machine_Agent.md
skills/artifact-storage/SKILL.md
skills/postgresql-persistence/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/storage/__init__.py
src/tonevyra_agent/storage/artifacts.py
harness/scripts/verify_artifacts.py
```

## Required Behavior

Artifact write order:

```text
1. Write artifact to temp file in the same directory.
2. Flush/fsync when possible.
3. Atomic rename temp file to final path.
4. Calculate SHA-256 checksum and file size.
5. Register or update task_artifacts row.
6. Return artifact metadata.
```

ArtifactStorage must support:

```text
save_json
save_text
save_bytes
load_json
load_text
exists
verify_checksum
```

## Required Artifacts for Test

```text
test_artifact.json
test_artifact.txt
test_artifact.bin
```

## Do Not Implement

```text
Preview generation
Vision analysis
Lightroom request generation
Quality scoring
Remote storage
MinIO/S3
```

## Validation

```bash
python harness/scripts/verify_artifacts.py
```

## Stop Rule

After T-002 is complete, stop and wait for user approval before T-003.

---

# T-003: Folder Watcher + File Stabilization

## Goal

Detect supported image files in the input folder, ignore temporary/sidecar files, wait until files are stable, and create image_tasks.

## Read

```text
.docs/11_Folder_Watcher_File_Pipeline_Agent.md
.docs/07_Agent_Core_State_Machine_Agent.md
skills/folder-watcher/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/agent/__init__.py
src/tonevyra_agent/agent/watcher.py
harness/scripts/run_watcher_test.py
```

## Required Behavior

Supported default extensions:

```text
.cr3
.cr2
.nef
.arw
.dng
.jpg
.jpeg
```

Ignore silently:

```text
hidden files
.tmp
.part
.crdownload
.xmp
.DS_Store
files starting with ._
```

Unsupported visible files may create SKIPPED task with:

```text
UNSUPPORTED_FILE_TYPE
```

File stabilization must check file size across intervals before task creation.

## Required DB Effects

```text
create image_tasks row
record task_events row with watch_loop evidence
```

## Do Not Implement

```text
Preview generation
Vision analysis
Lightroom export
Quality gate
```

## Validation

```bash
python harness/scripts/run_watcher_test.py
```

## Stop Rule

After T-003 is complete, stop and wait for user approval before T-004.

---

# T-004: Metadata + 1024px Preview

## Goal

Extract EXIF/basic metadata and create a 1024px long-edge sRGB JPEG preview for model input.

## Read

```text
.docs/08_Vision_Analysis_Design_Agent.md
.docs/11_Folder_Watcher_File_Pipeline_Agent.md
.docs/05_Artifact_Storage_Specification_Agent.md
skills/image-metadata-preview/SKILL.md
skills/artifact-storage/SKILL.md
```

## Implement

```text
src/tonevyra_agent/images/__init__.py
src/tonevyra_agent/images/metadata.py
src/tonevyra_agent/images/preview.py
```

## Required Artifacts

```text
exif.json
preview_1024.jpg
```

## Required Behavior

```text
Read source image metadata.
Create 1024px long-edge sRGB JPEG preview.
Register metadata and preview artifacts.
Record metadata and preview stage results.
```

The model must never receive the original RAW directly.

## Do Not Implement

```text
Vision inference
Correction planning
Lightroom export
Quality scoring
```

## Validation

```text
EXIF artifact exists
preview artifact exists
preview long edge <= 1024px
preview is sRGB JPEG
artifact checksums are registered
```

## Stop Rule

After T-004 is complete, stop and wait for user approval before T-005.

---

# T-005: Mock Vision Backend

## Goal

Implement fixture-based vision analysis that returns schema-validated structured results without real Qwen.

## Read

```text
.docs/08_Vision_Analysis_Design_Agent.md
.docs/05_Artifact_Storage_Specification_Agent.md
skills/vision-analysis/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/vision/__init__.py
src/tonevyra_agent/vision/schemas.py
src/tonevyra_agent/vision/analyzer.py
src/tonevyra_agent/vision/model.py
harness/fixtures/vision/valid_underwater.json
harness/fixtures/vision/low_confidence.json
harness/fixtures/vision/invalid_schema.json
```

## Required Artifacts

```text
vision_prompt.txt
vision_raw_response.json
vision_structured.json
```

## Required Behavior

```text
Use TONEVYRA_VISION_BACKEND=mock.
Return fixture-based VisionAnalysisResult.
Validate schema.
Persist raw and structured outputs as artifacts.
Store stage summary in PostgreSQL.
```

## Do Not Implement

```text
Real Qwen
Remote API
Online model download
Lightroom adjustments
```

## Validation

```text
valid fixture passes
low confidence fixture triggers requires_review behavior
invalid schema fixture fails with MODEL_OUTPUT_INVALID
structured artifact is registered
```

## Stop Rule

After T-005 is complete, stop and wait for user approval before T-006.

---

# T-006: Correction Planner

## Goal

Convert structured vision analysis into safe, clamped Lightroom adjustment plans.

## Read

```text
.docs/09_Correction_Planner_Design_Agent.md
.docs/08_Vision_Analysis_Design_Agent.md
skills/correction-planner/SKILL.md
```

## Implement

```text
src/tonevyra_agent/correction/__init__.py
src/tonevyra_agent/correction/schemas.py
src/tonevyra_agent/correction/planner.py
```

## Required Artifact

```text
correction_plan.json
```

## Required Behavior

```text
Read VisionAnalysisResult.
Generate base_preset, style_target, adjustments_json, confidence, requires_review.
Clamp all Lightroom parameters to allowed ranges.
Record correction_plan stage summary.
```

## Do Not Implement

```text
Direct model-controlled Lightroom values
Lightroom request writing
Quality scoring
Automatic learning calibration
```

## Validation

```text
correction_plan.json exists
all adjustment values are clamped
low confidence analysis sets requires_review
no unsupported Lightroom parameter is emitted
```

## Stop Rule

After T-006 is complete, stop and wait for user approval before T-007.

---

# T-007: Fake Lightroom Bridge

## Goal

Implement a file-based fake Lightroom bridge that simulates Lightroom request/response and fake export generation.

## Read

```text
.docs/06_Lightroom_Plugin_Bridge_Agent.md
.docs/05_Artifact_Storage_Specification_Agent.md
skills/lightroom-bridge/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/lightroom/__init__.py
src/tonevyra_agent/lightroom/schemas.py
src/tonevyra_agent/lightroom/bridge.py
harness/fake_lightroom/fake_lightroom_worker.py
```

## Required Artifacts

```text
lightroom_request.json
lightroom_response.json
fake_export.jpg
```

## Required Behavior

```text
Use TONEVYRA_LIGHTROOM_BACKEND=fake.
Write request JSON to bridge/requests.
Fake worker reads request and writes response.
Fake export file is created.
Response is registered as artifact.
```

Request payload must use normalized absolute paths:

```text
source_path
export_path
```

## Do Not Implement

```text
Real Lightroom Lua plugin
Lightroom catalog editing
AI in Lua
DB writes from Lua
Quality scoring
```

## Validation

```text
request JSON is valid
response JSON is valid
fake export file exists
failure response is handled
no real Lightroom dependency exists
```

## Stop Rule

After T-007 is complete, stop and wait for user approval before T-008.

---

# T-008: Quality Gate

## Goal

Evaluate exported image and produce final PASS / REVIEW_REQUIRED / FAILED decision.

## Read

```text
.docs/10_Quality_Gate_Design_Agent.md
.docs/07_Agent_Core_State_Machine_Agent.md
skills/quality-gate/SKILL.md
```

## Implement

```text
src/tonevyra_agent/quality/__init__.py
src/tonevyra_agent/quality/schemas.py
src/tonevyra_agent/quality/scoring.py
src/tonevyra_agent/quality/analyzer.py
```

## Required Artifact

```text
quality_detail.json
```

## Required Scores

```text
exposure_score
color_score
sharpness_score
noise_score
saturation_score
underwater_cast_score
overall_score
```

## Thresholds

```text
PASS >= 85
REVIEW_REQUIRED 70-84
FAILED < 70
```

## Required DB Effects

```text
quality_results row saved
image_tasks final status updated
task_events quality_loop event recorded
```

## Do Not Implement

```text
Unlimited retry
Real human review UI
Automatic re-correction loop
```

## Validation

```text
quality_detail.json exists
quality_results row is saved
final decision is PASS / REVIEW_REQUIRED / FAILED
final task status is updated
```

## Stop Rule

After T-008 is complete, stop and wait for user approval before T-009.

---

# T-009: Worker Pipeline Integration

## Goal

Connect metadata, preview, mock vision, correction planner, fake Lightroom, and quality gate into one-photo processing.

## Read

```text
.docs/02_System_Architecture_Agent.md
.docs/07_Agent_Core_State_Machine_Agent.md
.docs/implementation/Tonevyra_AI_Implementation_Readiness_Agent_v2.md
skills/agent-worker-pipeline/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/agent/worker.py
src/tonevyra_agent/agent/runner.py
```

## Required Flow

```text
metadata
preview
vision
correction_plan
lightroom
export
quality
final status
```

## Required Behavior

```text
Process one queued image task.
Persist required artifacts before marking stage complete.
Record stage_results and task_events.
End in PASS / REVIEW_REQUIRED / FAILED.
```

## Do Not Implement

```text
Worker pool
Real Qwen
Real Lightroom
Dashboard
```

## Validation

```text
one task reaches PASS / REVIEW_REQUIRED / FAILED
required artifacts are registered
task_events show major transitions
no stage is marked complete before artifact persistence
```

## Stop Rule

After T-009 is complete, stop and wait for user approval before T-010.

---

# T-010: Smoke Pipeline Harness

## Goal

Add automated smoke harness proving that one sample photo can complete end-to-end through Mock Vision + Fake Lightroom.

## Read

```text
.docs/14_Testing_QA_Strategy_Agent.md
.docs/15_Development_Roadmap_Milestones_Agent.md
skills/testing-harness/SKILL.md
```

## Implement

```text
harness/scripts/run_smoke_pipeline.py
harness/scripts/verify_db_state.py
harness/scripts/verify_artifacts.py
```

## Required Behavior

```text
Reset runtime test area.
Insert or detect one sample input.
Run one-photo pipeline.
Verify final status.
Verify artifact metadata.
Verify required artifacts.
```

## Do Not Implement

```text
Real Lightroom
Real Qwen
Long batch benchmark
```

## Validation

```bash
python harness/scripts/run_smoke_pipeline.py
python harness/scripts/verify_db_state.py
python harness/scripts/verify_artifacts.py
```

## Stop Rule

After T-010 is complete, stop and wait for user approval before T-011.

---

# T-011: Recovery Loop

## Goal

Recover unfinished tasks after crash/shutdown using PostgreSQL state, artifact records, file existence, checksums, Lightroom response, and export existence.

## Read

```text
.docs/13_Crash_Recovery_Error_Handling_Agent.md
.docs/07_Agent_Core_State_Machine_Agent.md
skills/recovery-loop/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/agent/recovery.py
harness/scripts/run_recovery_test.py
```

## Required Artifact

```text
recovery_decision.json
```

## Required Behavior

```text
Find unfinished tasks.
Inspect current status.
Verify artifact records and files.
Verify Lightroom response/export existence when relevant.
Choose safest resume point.
Resume or fail safely.
Record recovery_loop event.
```

## Do Not Implement

```text
Recovery from file logs
Infinite retry
Ignoring inconsistent evidence
```

## Validation

```bash
python harness/scripts/run_recovery_test.py
```

## Stop Rule

After T-011 is complete, stop and wait for user approval before T-012.

---

# T-012: Loop Event Evidence

## Goal

Standardize loop event evidence for Watch, Processing, Quality, Recovery, Feedback, and Benchmark loops.

## Read

```text
.docs/00_Loop_Engineering_Global_Addendum_Agent.md
.docs/07_Agent_Core_State_Machine_Agent.md
.docs/14_Testing_QA_Strategy_Agent.md
skills/loop-engineering/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
src/tonevyra_agent/agent/loops.py
harness/scripts/verify_loop_events.py
```

## Required Behavior

Each autonomous loop event must include:

```text
loop_name
loop_iteration
event_type
from_status
to_status
reason
artifact references when available
```

If direct DB columns do not exist for loop fields, store loop evidence in:

```text
task_events.payload_json
```

## Do Not Implement

```text
Open-ended loops
Unbounded retries
New DB columns without migration ticket
```

## Validation

```bash
python harness/scripts/verify_loop_events.py
```

## Stop Rule

After T-012 is complete, stop and wait for user approval before T-013.

---

# T-013: Feedback Storage Foundation

## Goal

Create local feedback storage foundation for user feedback and manual edit delta artifacts.

## Read

```text
.docs/00_Loop_Engineering_Global_Addendum_Agent.md
.docs/06_Lightroom_Plugin_Bridge_Agent.md
.docs/09_Correction_Planner_Design_Agent.md
skills/feedback-learning/SKILL.md
skills/artifact-storage/SKILL.md
```

## Implement

```text
src/tonevyra_agent/learning/__init__.py
src/tonevyra_agent/learning/schemas.py
src/tonevyra_agent/learning/feedback.py
src/tonevyra_agent/learning/dataset_builder.py
```

## Required Artifacts

```text
user_feedback.json
manual_edit_delta.json
training_sample_manifest.json
```

## Required Behavior

```text
Store explicit user decision.
Store reason tags.
Store AI-applied settings snapshot references.
Store current settings snapshot references when available.
Create learning_samples candidate only when approved.
```

## Do Not Implement

```text
Automatic model fine-tuning
Silent learning from user behavior
Remote upload
Automatic planner rule rewrite
```

## Validation

```text
feedback_records row is saved
user_feedback.json exists
manual_edit_delta.json contract is defined
approved sample can create learning_samples row
```

## Stop Rule

After T-013 is complete, stop and wait for user approval before T-014.

---

# T-014: CLI Operations Completion

## Goal

Expose essential MVP operations through CLI without putting business logic inside CLI handlers.

## Read

```text
.docs/12_CLI_Operations_Agent.md
skills/cli-operations/SKILL.md
```

## Implement or Complete Commands

```text
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
tonevyra-agent loop-events TASK_ID
tonevyra-agent feedback sync TASK_ID
tonevyra-agent feedback approve TASK_ID
tonevyra-agent feedback reject TASK_ID --reason REASON
tonevyra-agent benchmark-models --sample-set harness
```

## Do Not Implement

```text
Business logic inside CLI command handlers
Dashboard
Server API
```

## Validation

```text
CLI commands call service/repository interfaces
doctor still passes
process FILE_PATH can run one task with mock/fake pipeline
retry requires explicit user command
```

## Stop Rule

After T-014 is complete, stop and wait for user approval before T-015.

---

# T-015: Security + Offline Harness

## Goal

Verify local-only operation and prevent external data transmission, online model downloads, and unsafe model loading.

## Read

```text
AGENTS.md
CLAUDE.md
.docs/14_Testing_QA_Strategy_Agent.md
.docs/08_Vision_Analysis_Design_Agent.md
skills/local-model-security/SKILL.md
skills/testing-harness/SKILL.md
```

## Implement

```text
harness/scripts/run_security_check.py
```

## Required Checks

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
No trust_remote_code=True
No remote API calls
No external URL image loading
No runtime model download
```

## Do Not Implement

```text
Real Qwen fine-tuning
Remote telemetry
External API fallback
```

## Validation

```bash
python harness/scripts/run_security_check.py
```

## Stop Rule

After T-015 is complete, stop and wait for user approval before T-016.

---

# T-016: Real Lightroom Lua PoC

## Goal

Connect the file-based Python bridge to a real Lightroom Classic Lua plugin proof of concept.

## Read

```text
.docs/06_Lightroom_Plugin_Bridge_Agent.md
skills/lightroom-bridge/SKILL.md
```

## Implement

```text
src/tonevyra_agent/lightroom/plugin/TonevyraAI.lrplugin/Info.lua
src/tonevyra_agent/lightroom/plugin/TonevyraAI.lrplugin/Main.lua
```

## Required Behavior

```text
Plugin loads in Lightroom Classic.
Python writes request JSON.
Lua reads request.
Lua applies adjustment/export command.
Lua writes response JSON.
Python reads response.
```

## Do Not Implement

```text
AI inside Lua
DB access inside Lua
Quality scoring inside Lua
Queue management inside Lua
Direct Lightroom catalog file modification from Python
```

## Validation

```text
PING request succeeds
APPLY_ADJUSTMENTS_AND_EXPORT request succeeds on a test photo
response JSON is valid
export file exists
```

## Stop Rule

After T-016 is complete, stop and wait for user approval before T-017.

---

# T-017: Local Qwen Backend

## Goal

Add a local-only Qwen vision backend after the mock/fake pipeline is stable, preserving Qwen2.5-VL 3B 4bit as a technical stable candidate and Qwen3-VL 4B 4bit/GGUF as the commercial/default candidate slot.

## Read

```text
.docs/08_Vision_Analysis_Design_Agent.md
.docs/14_Testing_QA_Strategy_Agent.md
skills/local-model-security/SKILL.md
skills/vision-analysis/SKILL.md
```

## Required Behavior

```text
Use local_files_only=True.
Do not use trust_remote_code=True.
Do not download models at runtime.
Do not send previews or metadata externally.
Model receives only 1024px sRGB JPEG preview + EXIF/basic metadata.
Return schema-validated VisionAnalysisResult.
Mock backend remains available.
```

## Do Not Implement

```text
Online model download
Remote inference
Direct Lightroom adjustment output
Default 7B model
```

## Validation

```text
local Qwen backend returns valid structured output
invalid model output is caught
security harness passes
mock backend remains available
```

## Stop Rule

After T-017 is complete, stop and wait for user approval before T-018.

---

# T-018: Model Benchmark Loop

## Goal

Compare Qwen2.5-VL 3B 4bit as the technical stable candidate and Qwen3-VL 4B 4bit/GGUF as the commercial/default candidate before considering default-model promotion.

## Read

```text
.docs/00_Loop_Engineering_Global_Addendum_Agent.md
.docs/15_Development_Roadmap_Milestones_Agent.md
.docs/08_Vision_Analysis_Design_Agent.md
skills/model-benchmark-loop/SKILL.md
skills/testing-harness/SKILL.md
```

## Required Metrics

```text
inference time
peak memory
JSON validity
quality impact
error rate
Lightroom simultaneous operation stability
10-photo stability
100-photo batch stability
```

## Required Artifact

```text
model_benchmark_result.json
```

## Do Not Implement

```text
Automatic default model promotion
Online benchmark upload
Silent model replacement
```

## Validation

```text
benchmark result artifact exists
Qwen3 4B is not promoted automatically
Qwen3 commercial/default promotion requires license review, benchmark evidence, rollback path, and human approval
promotion recommendation is evidence-based
rollback path is documented
```

## Stop Rule

After T-018 is complete, stop and report MVP/real-integration completion summary to the user.

---

## 11. First Agent Prompt for T-001

Use this exact prompt for the first implementation step.

```text
Read AGENTS.md first.
Then read CLAUDE.md.
Then read .docs/implementation/Tonevyra_AI_Implementation_Readiness_Agent_v2.md.
Then read .docs/implementation/Tonevyra_AI_Implementation_Work_Order_Agent_v2.md.

Also read:
- .docs/03_Data_Persistence_Architecture_Agent.md
- .docs/04_PostgreSQL_Database_Schema_Agent.md
- .docs/12_CLI_Operations_Agent.md
- skills/python-mvp-structure/SKILL.md
- skills/postgresql-persistence/SKILL.md
- skills/testing-harness/SKILL.md

Implement T-001 only.

Ticket:
T-001: Project Foundation + DB Persistence

Goal:
Create the initial Tonevyra AI Python project foundation and connect it to the existing PostgreSQL database.

Current product:
Tonevyra AI

Current package:
tonevyra_agent

Current CLI:
tonevyra-agent

Current database:
- PostgreSQL
- database: tonevyra_agent
- app user: tonevyra_app
- schema: public
- env var: TONEVYRA_DATABASE_URL

Existing database objects:
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

Required implementation:
1. Use Python 3.11.
2. Create the Python package structure under src/tonevyra_agent.
3. Add or update pyproject.toml.
4. Add or update .env.example.
5. Add or update README.md with setup and doctor instructions.
6. Implement src/tonevyra_agent/__init__.py.
7. Implement src/tonevyra_agent/main.py.
8. Implement src/tonevyra_agent/cli.py.
9. Implement src/tonevyra_agent/core/config.py.
10. Implement src/tonevyra_agent/core/enums.py.
11. Implement src/tonevyra_agent/core/errors.py.
12. Implement src/tonevyra_agent/db/database.py using SQLAlchemy.
13. Implement src/tonevyra_agent/db/models.py matching the existing PostgreSQL tables.
14. Implement src/tonevyra_agent/db/repositories.py with basic CRUD for:
    - image_tasks
    - task_events
    - task_artifacts
15. Implement CLI command:
    tonevyra-agent doctor
16. Implement a DB smoke test command or script.

doctor must verify:
- Python version
- .env loading
- required runtime folder existence
- PostgreSQL connection
- current_database() equals tonevyra_agent
- current_user equals tonevyra_app
- required tables exist
- v_task_summary view exists

DB smoke test must:
1. Create one test image_task row.
2. Create one test task_event row.
3. Read the test task back.
4. Delete the test task and related test rows.
5. Report success or failure.

Do not implement:
- T-002 or later tickets
- Watcher
- ArtifactStorage beyond basic folder checks
- Metadata extraction
- Preview generation
- Mock Vision
- Correction Planner
- Fake Lightroom
- Quality Gate
- Recovery Loop
- Feedback Sync
- Real Qwen
- Real Lightroom
- FastAPI
- React
- Redis
- Celery
- MinIO
- Worker pool

Do not:
- create database tables
- drop database tables
- alter database tables
- create a new schema
- use SQLite as the main DB
- use postgres superuser for runtime app connection
- invent new status strings
- invent new stage names
- invent new error codes
- implement future scope early

Validation commands to run after implementation:
- python -m tonevyra_agent.cli doctor
- python -m tonevyra_agent.cli db-smoke-test

Important workflow rule:
After finishing T-001, stop immediately.
Do not start T-002.
Do not continue to the next ticket automatically.
Wait for user approval before continuing.

Final report format:
Ticket ID:
Implemented scope:
Changed files:
Commands run:
Validation result:
Doctor result:
DB smoke test result:
Harness/test result:
Out-of-scope items not implemented:
Assumptions:
Blocked items:
Risks or follow-up notes:
Next recommended ticket:
Waiting for user approval:
```
