# CONTRACT_LIGHTROOM_APPLY_ADAPTER

## Status

T-019 role correction contract.

## Objective

The Lightroom Classic plugin must be a thin apply adapter. It receives Agent-created correction values through bridge request JSON, applies them inside Lightroom Classic, and writes result JSON.

## Boundary

### In scope for plugin

- Load in Lightroom Classic as `TonevyraAI.lrplugin`.
- Read request JSON from `runtime\bridge\lightroom_apply_requests`.
- Use `source_path` to identify the photo.
- Find an existing catalog photo by path or import/add the source image.
- Apply Develop settings or a preset.
- Write result JSON to `runtime\bridge\lightroom_apply_results`.
- Provide status/debug UI for bridge state.

### Out of scope for plugin

- Input folder watching.
- User image folder watching.
- Model inference.
- Correction plan generation.
- Quality scoring.
- DB decision making.
- Agent orchestration.
- Lightroom process lifecycle management.
- Main workflow based on selected Lightroom photo.

## Required request fields

- `schema_version`
- `request_id`
- `task_id`
- `source_path`
- `operation`
- `develop_settings` or `preset_path`
- `created_at`

## Required result fields

- `schema_version`
- `request_id`
- `task_id`
- `source_path`
- `status`
- `catalog_action`
- `applied_parameters` or `applied_preset`
- `completed_at`
- `error_code`
- `message`

## Failure semantics

The plugin must write a failure result if the source path cannot be imported/found, the request is invalid, Lightroom API calls fail, or parameters are unsupported. Requests must not disappear without a result.

## Harness failure conditions

A T-019 implementation fails if plugin code or T-019 implementation notes make the plugin responsible for:

- `runtime\input` monitoring.
- input-folder or user-image-folder watcher behavior.
- selected-photo product workflow.
- `getTargetPhoto` as the main target selection mechanism.
- AI/model calls.
- quality score computation.
- correction plan creation.

## Canonical test command

```powershell
cd F:\tonevyra_ai_agent
python .\harness\scripts\verify_lightroom_apply_adapter_role.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
```
