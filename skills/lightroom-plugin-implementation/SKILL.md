# Folder-Driven Lightroom Plugin Implementation Skill

## Purpose

Use this skill when implementing the real Tonevyra AI Lightroom Classic plugin for T-019.

The plugin must be a folder-driven Lightroom apply worker. It must not become an AI runtime, database client, model runner, quality scoring module, or Lightroom UI-current-photo correction tool.

## Required product behavior

The implementation must support this MVP flow:

```text
input folder photo added
→ folder watcher task
→ agent correction plan
→ agent Lightroom apply request JSON
→ Lightroom plugin worker applies Develop settings
→ Lightroom apply result JSON
→ DB/task_events evidence
```

## Non-negotiable invariant

Do not implement the basic product flow as:

```text
Lightroom UI-current-photo flow
→ plugin menu action
→ correction
```

A plugin menu may exist only for diagnostics, worker status, restart, or manual replay of an existing apply request.

## Required file locations

Prefer an existing project canonical path. If none exists, use:

```text
lightroom/TonevyraAI.lrplugin/
  Info.lua
  Init.lua
  Worker.lua
  Bridge.lua
  Json.lua
  README.md
```

If the existing project already uses this path, preserve it:

```text
src/tonevyra_agent/lightroom/plugin/TonevyraAI.lrplugin/
```

## Bridge apply request rules

The Python agent writes apply request JSON to:

```text
runtime/bridge/lightroom_apply_requests/<request_id>.json
```

Required request fields:

- `schema_version = "t019.lightroom_apply.request.v1"`
- `request_id`
- `request_origin = "tonevyra_agent"`
- `command = "APPLY_LIGHTROOM_SETTINGS"`
- `task_id`
- `source_path`
- `created_at`
- `develop_settings`
- `safety.non_destructive_required = true`

## Bridge apply result rules

The Lightroom plugin writes result JSON to:

```text
runtime/bridge/lightroom_apply_results/<request_id>.json
```

Required result fields:

- `schema_version = "t019.lightroom_apply.result.v1"`
- `request_id`
- `request_origin = "lightroom_plugin"`
- `command = "APPLY_LIGHTROOM_SETTINGS"`
- `task_id`
- `status = "applied" | "partial" | "failed"`
- `source_path`
- `applied_settings`
- `skipped_settings`
- `lightroom_result.worker_running`

## Banned responsibilities inside Lua plugin

- AI model loading
- image analysis
- correction planning
- quality scoring
- PostgreSQL direct access
- internet access
- source image overwrite/delete
- selecting a Lightroom photo as the normal task source

## Completion rule

The implementation is not complete until:

```bash
python harness/scripts/verify_lightroom_plugin_structure.py
python harness/scripts/run_lightroom_bridge_contract_test.py
python harness/scripts/run_lightroom_worker_mapping_test.py
python harness/scripts/verify_lightroom_live_test_evidence.py --evidence <apply_result_or_evidence_json>
```

and existing project harness still passes.

## T-029 Mask Worker Extension

For T-029, extend the existing Plugin worker/dispatcher rather than creating a second Plugin. Add native mask capability probing, pre/post Develop snapshots, safe rollback, and idempotent replay. UI automation, catalog modification, arbitrary request preset paths, radial-template fallback, generated XMP fallback, and semantic decisions in Lua remain prohibited.
