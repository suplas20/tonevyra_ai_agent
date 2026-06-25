# Tonevyra AI Agent Harness

The `harness/` directory is an acceptance gate for Tonevyra AI Agent. It does not only provide mock fixtures; it verifies that the agent follows the project rules, skills, contracts, security boundaries, recovery behavior, artifact discipline, and loop-evidence requirements.

## Harness Role

Harness checks should prove that:

- Real local model and real Lightroom Classic evidence are the required completion gate for new work.
- Mock Vision and Fake Lightroom may remain as regression diagnostics, but they are not sufficient completion evidence.
- PostgreSQL is the operational state source of truth.
- Artifact files exist, checksums match, and large payloads stay out of the database.
- `task_events.payload_json` contains loop evidence for autonomous product loops.
- Feedback learning stays local and uses `feedback_records`, `learning_samples`, and `training_sample_manifest.json`.
- Model code remains local-only, offline, and network-blockable.
- T-018 benchmark evidence does not automatically promote any model.
- T-019 keeps the Lightroom Classic plugin as a thin apply adapter, not an input folder watcher.

## Core Harnesses

| Harness | File | Purpose |
|---|---|---|
| Runtime reset | `harness/scripts/reset_runtime.py` | Create or clear runtime test folders safely. |
| Watcher | `harness/scripts/run_watcher_test.py` | Verify Agent-owned file detection, ignore rules, stabilization, and watch loop evidence. |
| Metadata/preview | `harness/scripts/run_metadata_preview_test.py` | Verify EXIF/basic metadata and 1024px sRGB preview artifacts. |
| Live runtime gate | `harness/scripts/verify_live_runtime_gate.py` | Verify active real local model + Lightroom configuration and optional live apply/export evidence. |
| Mock vision diagnostic | `harness/scripts/run_vision_mock_test.py` | Verify schema-validated mock analysis and vision artifacts as a regression diagnostic. |
| Qwen backend | `harness/scripts/run_qwen_backend_test.py` | Verify local-only Qwen backend boundaries with fake runtime. |
| Correction planner | `harness/scripts/run_correction_planner_test.py` | Verify clamped Lightroom adjustment plans. |
| Fake Lightroom diagnostic | `harness/scripts/run_fake_lightroom_test.py` | Verify file-based fake request/response/export behavior as a regression diagnostic. |
| T-019 Apply Adapter role | `harness/scripts/verify_lightroom_apply_adapter_role.py` | Verify that the real Lightroom plugin is an apply adapter and not a folder watcher, AI runner, quality gate, or selected-photo workflow. |
| Quality gate | `harness/scripts/run_quality_gate_test.py` | Verify scoring, decision, quality artifacts, and DB rows. |
| Worker pipeline | `harness/scripts/run_worker_pipeline_test.py` | Verify one task reaches a terminal status through the pipeline. |
| Smoke pipeline | `harness/scripts/run_smoke_pipeline.py` | Verify end-to-end mock/fake processing and required evidence. |
| Recovery | `harness/scripts/run_recovery_test.py` | Verify recovery decisions from durable DB/artifact evidence. |
| Loop events | `harness/scripts/verify_loop_events.py` | Verify canonical loop payloads in `task_events.payload_json`. |
| Feedback learning | `harness/scripts/verify_feedback_learning.py` | Verify local feedback records, learning samples, and manifest artifacts. |
| Security | `harness/scripts/run_security_check.py` | Verify offline env vars, no remote API fallback, no runtime downloads, no unsafe model loading. |
| Model benchmark | `harness/scripts/run_model_benchmark_test.py` | Verify T-018 metrics, candidate policy, rollback path, and no automatic promotion. |

## Recommended Sequential Validation

Run harnesses sequentially because several scripts use local runtime and database fixtures.

```powershell
cd F:\tonevyra_ai_agent
.\.venv\Scripts\python.exe -m compileall src harness tests
.\.venv\Scripts\python.exe harness/scripts/run_security_check.py
.\.venv\Scripts\python.exe -m pytest tests/test_security_harness.py
.\.venv\Scripts\python.exe -m tonevyra_agent.cli doctor
.\.venv\Scripts\python.exe harness/scripts/verify_live_runtime_gate.py
.\.venv\Scripts\python.exe harness/scripts/run_watcher_test.py
.\.venv\Scripts\python.exe harness/scripts/run_metadata_preview_test.py
.\.venv\Scripts\python.exe harness/scripts/run_vision_mock_test.py
.\.venv\Scripts\python.exe harness/scripts/run_qwen_backend_test.py
.\.venv\Scripts\python.exe harness/scripts/run_correction_planner_test.py
.\.venv\Scripts\python.exe harness/scripts/run_fake_lightroom_test.py
.\.venv\Scripts\python.exe harness/scripts/verify_lightroom_apply_adapter_role.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
.\.venv\Scripts\python.exe harness/scripts/run_model_benchmark_test.py
.\.venv\Scripts\python.exe harness/scripts/run_quality_gate_test.py
.\.venv\Scripts\python.exe harness/scripts/run_worker_pipeline_test.py
.\.venv\Scripts\python.exe harness/scripts/run_smoke_pipeline.py
.\.venv\Scripts\python.exe harness/scripts/verify_db_state.py
.\.venv\Scripts\python.exe harness/scripts/verify_artifacts.py --smoke
.\.venv\Scripts\python.exe harness/scripts/run_recovery_test.py
.\.venv\Scripts\python.exe harness/scripts/verify_loop_events.py
.\.venv\Scripts\python.exe harness/scripts/verify_feedback_learning.py
.\.venv\Scripts\python.exe harness/scripts/verify_cli_operations.py
```

If the real Lightroom plugin has not been implemented yet, run the T-019 role harness without `--plugin-dir` to validate contracts and fixtures only:

```powershell
.\.venv\Scripts\python.exe harness/scripts/verify_lightroom_apply_adapter_role.py --project-root F:\tonevyra_ai_agent
```

## Environment

Use Tonevyra names as primary environment variables.

```env
TONEVYRA_DATABASE_URL=postgresql+psycopg://tonevyra_app:<password>@localhost:5432/tonevyra_agent
TONEVYRA_RUNTIME_DIR=runtime
TONEVYRA_VISION_BACKEND=qwen3vl
TONEVYRA_LIGHTROOM_BACKEND=lightroom
TONEVYRA_MODEL_OFFLINE=true
TONEVYRA_WORKER_CONCURRENCY=1
TONEVYRA_QWEN3_MODEL_PATH=D:/Tonevyra/models/Qwen3-VL-4B-Instruct
TONEVYRA_MODEL_MANIFEST_PATH=models/qwen3-vl-4b-instruct/model_manifest.json
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
```

Legacy `MW_*` variables may remain as compatibility fallbacks in old harness helpers, but new documentation and new harness code should prefer `TONEVYRA_*`.

## T-019 Lightroom Apply Adapter Position

The Agent is responsible for input folder watching, analysis, correction planning, quality gates, DB evidence, and request creation. The Lightroom Classic plugin is responsible only for consuming an Agent-created apply request, locating/importing `source_path` in the Lightroom catalog, applying the supplied Develop settings or preset, and writing a result.

## Model Policy Gate

T-018 compares:

```text
Qwen2.5-VL-3B: technical stable candidate
Qwen3-VL-4B: commercial/default candidate
```

Qwen3 commercial/default promotion is blocked until license review, local benchmark evidence, Lightroom simultaneous stability, rollback documentation, and explicit human approval are complete.


## T-020 Lightroom Final Export Adapter

T-020 verifies automatic export of the corrected Lightroom catalog rendition after a valid T-019 apply result.

Static contract and fixture verification:

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent
```

Plugin source boundary verification:

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin --strict
```

Real result and output-file evidence verification:

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin --result-json <result-json> --require-output-file --strict
```

A T-020 success requires both `status=exported` and an actual non-empty output file. T-019 Apply Adapter files and tests remain mandatory regression gates.

## T-021 Dual-Mode Agent Core and Closed-Loop Quality Reprocessing

T-021 verifies that one Common Agent Core can select Module or Model Providers through plan policy, while all Provider outputs use a common normalized schema and cannot bypass the Adjustment Planner. It also verifies that post-export quality evaluation produces bounded retries and separates technical failure, source limitation, final failure, and approval.

Static contract and fixture verification:

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent
```

Runtime evidence verification:

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent --job-evidence <job-manifest.json> --strict
```

Run T-019 Apply Adapter and T-020 Final Export Adapter verifiers before T-021. T-021 requires all 25 baseline skills and adds two new skills for a cumulative total of 27.
