# T-019 Folder-Driven Lightroom Plugin Contract

## Purpose

This contract prevents the Lightroom implementation from drifting back into a Lightroom UI-current-photo workflow.

## Required product flow

```text
input folder file
→ folder watcher
→ Python agent task
→ correction plan
→ Lightroom apply request
→ Lightroom plugin worker
→ Lightroom apply result
→ DB/task_events evidence
```

## Plugin identity

The plugin must include:

- `Info.lua`
- `LrToolkitIdentifier`
- `LrPluginName`
- `Tonevyra AI` identity
- init/background worker entrypoint, such as `LrInitPlugin` or an equivalent worker bootstrap

## Required bridge tokens

Lua plugin source must include or reference:

- `lightroom_apply_requests`
- `lightroom_apply_results`
- `APPLY_LIGHTROOM_SETTINGS`
- `source_path`
- `task_id`
- `develop_settings`
- `applied_settings`
- `skipped_settings`

## Forbidden implementation patterns

Lua plugin source must not include:

- Lightroom current-selection APIs as the normal request source
- plugin-created apply requests
- user menu commands that start photo correction directly
- AI/model runtime code
- PostgreSQL or SQLite client code
- external HTTP/network calls
- source image overwrite/delete behavior

## Apply request schema

- `schema_version = t019.lightroom_apply.request.v1`
- `request_origin = tonevyra_agent`
- `command = APPLY_LIGHTROOM_SETTINGS`

## Apply result schema

- `schema_version = t019.lightroom_apply.result.v1`
- `request_origin = lightroom_plugin`
- `command = APPLY_LIGHTROOM_SETTINGS`

## Evidence rule

Evidence must prove folder-driven automation, not selected-photo execution.
