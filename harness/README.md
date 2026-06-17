# Tonevyra AI Agent Harness

The `harness/` directory is an acceptance gate for Tonevyra AI Agent. It does not only provide mock fixtures; it verifies that the agent follows the project rules, skills, contracts, security boundaries, recovery behavior, artifact discipline, and loop-evidence requirements.

## Harness Role

Harness checks should prove that:

- Mock Vision passes before real local model integration.
- Fake Lightroom passes before real Lightroom Lua plugin integration.
- PostgreSQL is the operational state source of truth.
- Artifact files exist, checksums match, and large payloads stay out of the database.
- `task_events.payload_json` contains loop evidence for autonomous product loops.
- Feedback learning stays local and uses `feedback_records`, `learning_samples`, and `training_sample_manifest.json`.
- Model code remains local-only, offline, and network-blockable.
- T-018 benchmark evidence does not automatically promote any model.

## Core Harnesses

| Harness | File | Purpose |
|---|---|---|
| Runtime reset | `harness/scripts/reset_runtime.py` | Create or clear runtime test folders safely. |
| Watcher | `harness/scripts/run_watcher_test.py` | Verify file detection, ignore rules, stabilization, and watch loop evidence. |
| Metadata/preview | `harness/scripts/run_metadata_preview_test.py` | Verify EXIF/basic metadata and 1024px sRGB preview artifacts. |
| Mock vision | `harness/scripts/run_vision_mock_test.py` | Verify schema-validated mock analysis and vision artifacts. |
| Qwen backend | `harness/scripts/run_qwen_backend_test.py` | Verify local-only Qwen backend boundaries with fake runtime. |
| Correction planner | `harness/scripts/run_correction_planner_test.py` | Verify clamped Lightroom adjustment plans. |
| Fake Lightroom | `harness/scripts/run_fake_lightroom_test.py` | Verify file-based bridge request/response/export behavior. |
| Lightroom plugin PoC | `harness/scripts/verify_lightroom_plugin_poc.py` | Verify real plugin files and bridge protocol boundaries. |
| T-019 plugin structure | `harness/scripts/verify_lightroom_plugin_structure.py` | Verify folder-driven plugin identity, bridge tokens, and forbidden implementation patterns. |
| T-019 bridge contract | `harness/scripts/run_lightroom_bridge_contract_test.py` | Verify apply request/result schemas and folder-driven fixture contract. |
| T-019 worker mapping | `harness/scripts/run_lightroom_worker_mapping_test.py` | Verify allowed Develop parameter clamp/skipped behavior. |
| T-019 live evidence | `harness/scripts/verify_lightroom_live_test_evidence.py` | Verify real or fixture apply-result evidence from the Lightroom plugin. |
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
.\.venv\Scripts\python.exe -m compileall src harness tests
.\.venv\Scripts\python.exe harness/scripts/run_security_check.py
.\.venv\Scripts\python.exe -m pytest tests/test_security_harness.py
.\.venv\Scripts\python.exe -m tonevyra_agent.cli doctor
.\.venv\Scripts\python.exe harness/scripts/run_watcher_test.py
.\.venv\Scripts\python.exe harness/scripts/run_metadata_preview_test.py
.\.venv\Scripts\python.exe harness/scripts/run_vision_mock_test.py
.\.venv\Scripts\python.exe harness/scripts/run_qwen_backend_test.py
.\.venv\Scripts\python.exe harness/scripts/run_correction_planner_test.py
.\.venv\Scripts\python.exe harness/scripts/run_fake_lightroom_test.py
.\.venv\Scripts\python.exe harness/scripts/verify_lightroom_plugin_poc.py
.\.venv\Scripts\python.exe harness/scripts/verify_lightroom_plugin_structure.py --plugin-dir plugin_scaffold/TonevyraAI.lrplugin
.\.venv\Scripts\python.exe harness/scripts/run_lightroom_bridge_contract_test.py
.\.venv\Scripts\python.exe harness/scripts/run_lightroom_worker_mapping_test.py
.\.venv\Scripts\python.exe harness/scripts/verify_lightroom_live_test_evidence.py --evidence harness/fixtures/lightroom_plugin/valid_apply_result.json
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

## Environment

Use Tonevyra names as primary environment variables.

```env
TONEVYRA_DATABASE_URL=postgresql+psycopg://tonevyra_app:<password>@localhost:5432/tonevyra_agent
TONEVYRA_RUNTIME_DIR=runtime
TONEVYRA_VISION_BACKEND=mock
TONEVYRA_LIGHTROOM_BACKEND=fake
TONEVYRA_MODEL_OFFLINE=true
TONEVYRA_WORKER_CONCURRENCY=1
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
```

Legacy `MW_*` variables may remain as compatibility fallbacks in old harness helpers, but new documentation and new harness code should prefer `TONEVYRA_*`.

## Model Policy Gate

T-018 compares:

```text
Qwen2.5-VL-3B: technical stable candidate
Qwen3-VL-4B: commercial/default candidate
```

Qwen3 commercial/default promotion is blocked until license review, local benchmark evidence, Lightroom simultaneous stability, rollback documentation, and explicit human approval are complete.
