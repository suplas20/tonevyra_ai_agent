# CLAUDE.md

Read and follow `AGENTS.md` before making any code changes.

`AGENTS.md` is mandatory and has priority over all other project notes. After reading it, read the relevant `skills/*/SKILL.md` file for the implementation area.

Do not implement features outside MVP scope unless explicitly requested. If a request conflicts with `AGENTS.md`, stop and report the conflict instead of implementing it.

---

## Tonevyra AI naming rule

The current product name is Tonevyra AI.

Use these canonical names in new implementation:

```text
Product name: Tonevyra AI
Full technical name: Tonevyra AI Agent
Python package: tonevyra_agent
CLI command: tonevyra-agent
PostgreSQL database: tonevyra_agent
PostgreSQL app role: tonevyra_app
Primary DB env var: TONEVYRA_DATABASE_URL
Lightroom plugin folder: TonevyraAI.lrplugin
```

Do not introduce new `mw_photo_agent`, `MWPhotoAgent`, or `mw-agent` names in new code. Those are legacy references only. Temporary aliases may exist only for migration compatibility.

---

## Response language rule

User-facing explanations, progress updates, final reports, and implementation summaries must be written in Korean unless the user explicitly asks for another language.

Code identifiers, commands, file paths, logs, database object names, environment variable names, and quoted tool output may remain in their original language.

---

## Required reading for database work

Before implementing or modifying database, persistence, ORM, repository, migration, recovery, artifact metadata, or DB harness code, read:

```text
AGENTS.md
skills/postgresql-persistence/SKILL.md
skills/artifact-storage/SKILL.md
skills/testing-harness/SKILL.md
```

If a skill file is missing, stop and report that the required skill document is missing before implementing the area.

Database implementation rules:

```text
- Runtime app connection must use TONEVYRA_DATABASE_URL.
- Runtime app connection must use tonevyra_app, not postgres.
- tonevyra_agent is the single product database in MVP.
- The public schema contains the product tables.
- DBeaver SQL is bootstrap/inspection only.
- Future schema changes must be done through Alembic migrations.
- SQLAlchemy models must match the live PostgreSQL schema.
- Do not add SQLite as an operational fallback.
- Do not store image binaries, previews, exports, raw model payloads, or debug logs as DB blobs.
```

Required MVP database objects:

```text
image_tasks
task_artifacts
task_events
stage_results
quality_results
feedback_records
learning_samples
v_task_summary
```

---

## Required reading for autonomous agent behavior

Before implementing any autonomous behavior, retry behavior, watcher behavior, worker pipeline behavior, recovery behavior, quality decision behavior, feedback behavior, or model benchmark behavior, read:

```text
skills/loop-engineering/SKILL.md
skills/feedback-learning/SKILL.md
skills/testing-harness/SKILL.md
```

Loop engineering in this project means the finished product agent's automatic work-loop design. It does not mean the software development process.

Autonomous product behavior must be implemented as explicit bounded loops with:

```text
- entry condition
- allowed actions
- state transitions
- retry limit
- timeout
- exit condition
- failure condition
- human review condition
- persisted evidence
- harness verification
```

Do not create open-ended loops, unbounded retries, hidden background training, external training calls, or model fine-tuning during normal photo processing.

---

## Feedback learning rule

The system may collect local learning data from user feedback and user Lightroom behavior.

The first learning target is Correction Planner calibration. Direct vision-model fine-tuning is a later offline, opt-in, versioned, benchmarked, reversible process.

All feedback learning data must remain local. Do not send images, previews, prompts, metadata, correction results, manual edit deltas, feedback, or training candidates to external services.

MVP feedback implementation must stop at:

```text
- feedback_records persistence
- learning_samples candidate registration
- manual edit delta capture when available
- local dataset candidate artifact creation
```

Do not implement automatic fine-tuning in MVP.

---

## Required reading for model work

Before implementing a real model backend, read:

```text
AGENTS.md
skills/model-security/SKILL.md
skills/vision-analysis/SKILL.md
skills/testing-harness/SKILL.md
```

Model backend rules:

```text
- MockVisionBackend must pass before QwenVisionBackend is connected.
- Qwen is a replaceable backend candidate, not a hard dependency.
- Use local model files only.
- Use local_files_only=True.
- Do not use trust_remote_code=True.
- Do not download model files during photo processing.
- Do not call remote APIs.
- Do not load images from external URLs.
- Keep model worker network-blockable at OS firewall level.
```

---

## Implementation behavior

When modifying code:

```text
1. Read AGENTS.md first.
2. Read the relevant skill file before editing.
3. Preserve the Tonevyra naming policy.
4. Keep the MVP CLI-first.
5. Keep worker concurrency at 1 unless AGENTS.md is explicitly updated.
6. Add or update tests/harness checks for the changed behavior.
7. Do not introduce dashboard, FastAPI-first, Redis, Celery, MinIO, message broker, or worker pool code in MVP.
8. Do not invent new status strings, stage strings, error codes, artifact types, or quality decisions without updating AGENTS.md, code enums, DB constraints, migrations, and tests together.
```

If implementation requires changing a project rule, stop and ask for approval before changing code.


---

## Required reading for T-020 Lightroom export work

Before implementing or modifying corrected-image export, Lightroom export requests/results, export recovery, export file verification, or `EXPORT_DONE` transitions, read:

```text
AGENTS.md
.docs/t020/T-020_Lightroom_Final_Export_Adapter_Work_Order.md
skills/lightroom-apply-adapter/SKILL.md
skills/lightroom-final-export-adapter/SKILL.md
skills/lightroom-bridge/SKILL.md
skills/artifact-storage/SKILL.md
skills/recovery-error-handling/SKILL.md
skills/testing-harness/SKILL.md
```

T-020 implementation rules:

```text
- Preserve all completed T-019 behavior and files.
- Create export requests only after a verified T-019 applied result.
- Use absolute source_path and export_path values.
- The normal workflow must be automatic bridge processing, not manual Lightroom export.
- Default MVP export is JPEG quality 95, sRGB, no resize, no overwrite.
- Do not report success unless the expected output file exists and has non-zero size.
- Do not set EXPORT_DONE before result, file, checksum/artifact, and DB evidence are valid.
- Keep retry and timeout bounded and recoverable.
- Do not modify Vision, Correction Planner, or Quality Gate algorithms for T-020.
- Do not add new status or error code values without synchronized rule, enum, DB, migration, recovery, fixture, and test updates.
```

Canonical T-020 harness:

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin --strict
```

---

## Required reading for T-021 dual-mode agent and closed-loop work

Before modifying Common Agent Core, provider selection, Module/Model analysis, quality evaluation, retry behavior, new failure classes, or T-021 states, read:

```text
AGENTS.md
.docs/t021/T-021_Dual_Mode_Photo_Agent_Core_Work_Order.md
.docs/t021/T-021_Implementation_Specification.md
skills/dual-mode-agent-core/SKILL.md
skills/closed-loop-quality-reprocessing/SKILL.md
skills/correction-planner/SKILL.md
skills/lightroom-apply-adapter/SKILL.md
skills/lightroom-final-export-adapter/SKILL.md
skills/artifact-storage/SKILL.md
skills/testing-harness/SKILL.md
```

T-021 implementation rules:

```text
- Preserve all 25 T-020 baseline skills and all T-019/T-020 harness files.
- Add, do not merge, the dual-mode-agent-core and closed-loop-quality-reprocessing skills.
- Build one Common Agent Core; do not create separate free and paid repositories.
- Complete ModuleAnalysisProvider and ModuleQualityProvider first.
- Keep Model Provider behind the same normalized schema.
- Reject model output that includes direct Lightroom adjustments, Develop settings, preset paths, or final decisions.
- Adjustment Planner remains the only component that creates bounded Lightroom values.
- Do not begin quality evaluation before T-020 export result and actual output-file evidence are valid.
- Keep Plugin responsibility technical; Plugin must not score quality or decide retries.
- Separate TECHNICAL_FAILED from RETRY_REQUIRED, SOURCE_LIMITED, and FINAL_FAILED.
- Create a new immutable attempt and new request IDs for every quality retry.
- Respect plan-specific retry budgets and progress guards.
- Do not automatically switch to a remote model or silently fall back between providers.
- Keep legacy statuses readable and use additive migrations.
```

Required verification order:

```powershell
python .\harness\scripts\verify_lightroom_apply_adapter_role.py --project-root F:\tonevyra_ai_agent
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent
```

When runtime evidence exists:

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent --job-evidence <job-manifest.json> --strict
```


---

## Required reading for T-029 Lightroom native masking work

Scope update, 2026-06-29: radial-gradient / radial-template fallback is excluded from T-029. Treat older radial fallback wording in T-029 docs as superseded until the docs are fully renamed. T-029 allows native mask execution only for targets actually detected by supported Lightroom native mask types; native detection failure must produce `skip_local` or `review_required`.

Before modifying semantic target geometry, local mask planning, Lightroom mask requests/results, Plugin native-mask application, mask rollback, or local color quality evidence, read:

```text
AGENTS.md
.docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md
.docs/t029/T-029_Implementation_Specification.md
.docs/t029/T-029_Lightroom_Live_Test_Checklist.md
.docs/t029/T-029_Seed_Radial_Preset_Preparation_Guide.md
.docs/t023/T-023_Semantic_Subject_Analysis_Local_Adjustment_Work_Order.md
.docs/t028/T-028_Production_Reliability_Agent_Operations_Work_Order.md
skills/semantic-subject-analysis/SKILL.md
skills/lightroom-local-adjustment-planning/SKILL.md
skills/lightroom-radial-mask-execution/SKILL.md
skills/radial-mask-template-library/SKILL.md
skills/lightroom-apply-adapter/SKILL.md
skills/lightroom-plugin-implementation/SKILL.md
skills/recovery-error-handling/SKILL.md
skills/testing-harness/SKILL.md
harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md
```

T-029 implementation rules:

```text
- Preserve all 41 T-028 baseline skills and add the two T-029 skills; total 43.
- Reuse the current Apply Adapter, bridge dispatcher, Planner, attempt model, and recovery system.
- Do not build or use a radial template library for T-029.
- Stop with explicit `review_required` or `skip_local` evidence when the intended target is not detected by native masks.
- Provider output remains semantic evidence only.
- Planner selects native-only strategy and bounded values.
- Plugin executes validated native-mask plans only.
- Geometry is oriented normalized 0..1.
- Existing user masks must be preserved.
- Same idempotency key must not duplicate a mask.
- Do not use radial fallback, UI automation, catalog modification, arbitrary runtime XMP generation, or silent global fallback.
- Do not add a new top-level task state for T-029.
- Real completion requires static, deterministic runtime, strict live Lightroom, and T-019..T-028 regression evidence.
```

Canonical commands:

```powershell
python .\harness\scripts\verify_t029_lightroom_radial_masking.py --project-root .
python .\harness\scripts\run_t029_radial_masking_runtime.py --project-root . --output runtime\t029_runtime_evidence.json --regressions-passed
python .\harness\scripts\verify_t029_lightroom_radial_masking.py --project-root . --runtime-evidence runtime\t029_runtime_evidence.json
python .\harness\scripts\verify_t029_lightroom_radial_masking.py --project-root . --runtime-evidence runtime\t029_runtime_evidence.json --live-evidence <live-evidence.json> --strict
```

## Required reading for T-030 Windows background/tray work

Before implementing or modifying Windows background execution, folder watcher runtime, tray UI, single instance, autostart, Worker supervision, or Windows shutdown behavior, read:

```text
AGENTS.md
.docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md
.docs/t030/T-030_Implementation_Specification.md
.docs/t030/T-030_Windows_Live_Test_Checklist.md
.docs/t030/T-030_Tray_Icon_Asset_Guide.md
skills/folder-watcher/SKILL.md
skills/resumable-idempotent-jobs/SKILL.md
skills/production-reliability-operations/SKILL.md
skills/windows-background-agent-lifecycle/SKILL.md
skills/system-tray-operations/SKILL.md
skills/testing-harness/SKILL.md
harness/CONTRACT_T030_WINDOWS_BACKGROUND_TRAY.md
```

T-030 implementation rules:

```text
- Build a per-user Windows application, not a Windows Service.
- Keep Tray Shell thin; Worker owns all pipeline business logic.
- Use PostgreSQL as the durable queue; do not add SQLite.
- Coalesce file events and prove stability before queueing.
- Keep main model and Lightroom concurrency at 1.
- Enforce per-user single instance for Tray and Worker.
- Use bounded heartbeat/restart and T-028 recovery.
- Preserve source files and prevent output recursion.
- Use approved Tonevyra symbol source for production tray icons.
- Reference harness output is not real Windows completion evidence.
```

Stop after T-030 and wait for approval before packaging or code-protection work.

## Required reading for T-031

Before macOS, platform adapter, inference process, GPU memory, MPS, FSEvents, menu bar, or idle-unload work, read:

```text
AGENTS.md
.docs/t031/T-031_macOS_Apple_Silicon_Runtime_and_Idle_VRAM_Work_Order.md
.docs/t031/T-031_Implementation_Specification.md
skills/macos-apple-silicon-runtime/SKILL.md
skills/inference-worker-memory-lifecycle/SKILL.md
skills/testing-harness/SKILL.md
```

Do not claim T-031 complete from reference runtime only. Real macOS and Windows VRAM evidence are separate hard gates.
