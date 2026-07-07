# Tonevyra AI Agent Task Update Impact Report

## Scope

This report reviews completed work T-001 through T-018 against the updated harness, skill, and PRD expectations. The review preserves the existing implementation and changes only the parts that conflicted with the updated acceptance-gate and model-policy language.

## Updated Policy Baseline

- Harnesses are acceptance gates, not just mock runtimes.
- `task_events.payload_json` is the MVP location for loop evidence.
- Feedback learning uses `feedback_records`, `learning_samples`, and `training_sample_manifest.json`.
- `TONEVYRA_*`, `tonevyra_agent`, and `Tonevyra AI` are canonical.
- Legacy `MW_*` fallback may remain only for compatibility.
- Qwen2.5-VL-3B is a technical stable candidate.
- Qwen3-VL-4B is the commercial/default candidate, but promotion requires license review, benchmark evidence, rollback path, and human approval.

## Task-by-Task Impact

| Task | Area | Harness/Skill Mapping | Classification | Applied Change | Remaining Risk |
|---|---|---|---|---|---|
| T-001 | Project foundation + DB persistence | `postgresql-persistence`, `testing-harness`, doctor, DB smoke | Document/package update only | `pyproject.toml` now packages only `tonevyra_agent*`; README uses Tonevyra commands. | Live DB validation depends on local PostgreSQL availability. |
| T-002 | Artifact storage | `artifact-storage`, `verify_artifacts.py` | Change not required | Existing atomic artifact/checksum design aligns with policy. | None identified beyond live artifact verification. |
| T-003 | Folder watcher | `folder-watcher`, watch loop evidence | Harness/doc update only | Harness README now frames watcher as acceptance gate; compatibility fallback retained. | None identified. |
| T-004 | Metadata + preview | `image-metadata-preview`, `vision-analysis` | Change not required | Existing 1024px preview + metadata contract remains aligned. | None identified. |
| T-005 | Mock vision backend | `vision-analysis`, mock-first policy | Change not required | Mock backend remains available and first-class. | None identified. |
| T-006 | Correction planner | `correction-planner`, model role rule | Change not required | Planner remains separate from model output and clamps adjustments. | None identified. |
| T-007 | Fake Lightroom bridge | `lightroom-bridge`, fake before real | Documentation update only | Harness README clarifies fake bridge as an acceptance gate. | None identified. |
| T-008 | Quality gate | `quality-gate`, `quality_loop` | Change not required | Existing quality result and loop evidence structure aligns. | Human tuning of thresholds remains future work. |
| T-009 | Worker pipeline | `agent-worker-pipeline`, processing loop | Change not required | Existing worker pipeline remains the orchestrator; no worker pool added. | Live DB/runtime fixtures required for full validation. |
| T-010 | Smoke pipeline harness | `testing-harness`, artifact/DB verification | Documentation update only | Harness README now lists smoke as evidence gate, not demo runtime. | None identified. |
| T-011 | Recovery loop | `recovery-loop`, `recovery-error-handling` | Change not required | Recovery still relies on DB + artifacts, not logs. | None identified. |
| T-012 | Loop event evidence | `loop-engineering`, `verify_loop_events.py` | Change not required | `task_events.payload_json` already carries canonical loop payloads. | None identified. |
| T-013 | Feedback storage foundation | `feedback-learning`, `verify_feedback_learning.py` | Change not required | `feedback_records`, `learning_samples`, `training_sample_manifest.json` are already used. | Real Lightroom settings sync remains a future integration detail. |
| T-014 | CLI operations | `cli-operations` | Documentation update only | README now documents `tonevyra-agent` commands. | CLI doctor requires local PostgreSQL. |
| T-015 | Security + offline harness | `local-model-security`, `model-security` | Skill/doc update only | Model security skill now reflects Qwen3 commercial/default gate. | Actual model install must still be performed manually and locally. |
| T-016 | Real Lightroom Lua PoC | `lightroom-bridge`, plugin boundary checks | Change not required | Plugin remains file-based and does not run AI/DB/quality logic. | Real Lightroom Classic export must be validated outside local static harness if not already done. |
| T-017 | Local Qwen backend | `model-security`, `vision-analysis` | Policy/document update only | Work Order now describes Qwen2.5 technical candidate plus Qwen3 commercial/default candidate slot. | Actual model files are not present in `models/`; local installation remains separate. |
| T-018 | Model benchmark loop | `model-benchmark-loop`, `testing-harness` | Code + harness update required | Candidate roles changed to `technical_stable_candidate` and `commercial_default_candidate`; harness asserts license-review gate wording. | Lightroom simultaneous stability remains explicitly unmeasured in the local fake-runtime harness. |

## T-018 Priority Review

T-018 already produced bounded benchmark evidence, required metrics, rollback path, no online upload, and no automatic promotion. The updated model policy required clearer candidate semantics:

- Before: Qwen2.5 was labeled `stable_candidate`; Qwen3 was labeled `validation_candidate`.
- After: Qwen2.5 is labeled `technical_stable_candidate`; Qwen3 is labeled `commercial_default_candidate`.

The benchmark still does not promote Qwen3 automatically. It continues to require 100-photo stability and Lightroom simultaneous operation stability before eligibility. The updated harness additionally checks that Qwen3 policy mentions license review.

## Files Changed

- `src/tonevyra_agent/vision/benchmark.py`
- `harness/scripts/run_model_benchmark_test.py`
- `AGENTS.md`
- `skills/model-security/SKILL.md`
- `skills/README.md`
- `skills/project-scope/SKILL.md`
- `harness/README.md`
- `harness/scripts/_common.py`
- `harness/scripts/reset_runtime.py`
- `harness/prompts/02_security_harness_prompt.md`
- `README.md`
- `.env.example`
- `pyproject.toml`
- `.gitignore`
- `.docs/implementation/Tonevyra_AI_Implementation_Work_Order_Agent_v2.md`
- repeated `.docs/*.md` model candidate wording updates

## Out of Scope

- No DB schema change was made.
- No new status, stage, error code, artifact type, or quality decision was added.
- No real model download or remote API was introduced.
- Legacy `src/mw_photo_agent` files have since been removed; package discovery now includes only the active Tonevyra packages.
