# Lightroom Bridge Skill

## Purpose
Use a file-based JSON bridge between Python and Lightroom Classic or the fake Lightroom worker.

The bridge transports already-validated correction plans. It must not decide AI corrections by itself.

## Rules
- Python writes request JSON.
- Lightroom/fake worker writes response JSON.
- Python reads response and updates DB/artifacts.
- Request payload must use normalized absolute `source_path` and `export_path`.
- Request values must come from Correction Planner, not raw model output.
- Response handling must be idempotent; duplicate responses should not corrupt task state.
- Timeouts and stale processing files use structured error codes.
- Store request/response artifacts and checksums.

## Required Artifacts
`lightroom_request.json`, `lightroom_response.json`.

## Do Not
- Do not run AI inside Lua.
- Do not access PostgreSQL from Lua.
- Do not quality-score inside Lua.
- Do not modify Lightroom catalog files directly from Python.
- Do not rely on relative paths in request payloads.

## Harness Validation
- `harness/scripts/run_fake_lightroom_test.py`
- `harness/scripts/verify_lightroom_plugin_poc.py`
