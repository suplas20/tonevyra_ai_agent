# Lightroom Apply Adapter Skill

## Purpose

Use this skill for T-019 after the Lightroom role correction.

The Lightroom Classic plugin is a **Lightroom Apply Adapter**. It does not watch image folders, analyze photos, generate correction plans, compute quality scores, or orchestrate the product pipeline. Its only product responsibility is to receive an Agent-created apply request and apply the supplied correction values inside Lightroom Classic.

## Canonical Project Paths

```text
Project root: F:\tonevyra_ai_agent
Plugin: F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
Bridge root: F:\tonevyra_ai_agent\runtime\bridge
Apply requests: F:\tonevyra_ai_agent\runtime\bridge\lightroom_apply_requests
Apply results: F:\tonevyra_ai_agent\runtime\bridge\lightroom_apply_results
Input folder: F:\tonevyra_ai_agent\runtime\input
```

The plugin may read the bridge request directory and write the bridge result directory. The plugin must not watch or scan the input folder.

## Role Separation

### Python Agent owns

1. Watching the user image/input folder.
2. Creating image tasks.
3. Reading metadata and generating previews.
4. Running vision analysis.
5. Creating the correction plan.
6. Running quality gates.
7. Creating Lightroom apply request JSON.
8. Recording DB evidence and `task_events.payload_json`.
9. Collecting Lightroom apply results.

### Lightroom Plugin owns

1. Loading in Lightroom Classic as `TonevyraAI.lrplugin`.
2. Reading request JSON from `runtime\bridge\lightroom_apply_requests`.
3. Validating `request_id`, `task_id`, `source_path`, and the correction payload.
4. Finding the photo in the Lightroom catalog by path or importing/adding it if absent.
5. Applying the supplied Develop settings or applying a supplied/generated preset.
6. Writing result JSON to `runtime\bridge\lightroom_apply_results`.
7. Showing lightweight status/debug information for bridge processing.

## Prohibited Plugin Behavior

The plugin must not:

- Watch `runtime\input`.
- Watch a user-selected image work folder.
- Detect new image files by itself.
- Generate a correction plan.
- Run AI/model inference.
- Compute quality scores or make quality gate decisions.
- Access PostgreSQL/SQLite or make DB decisions.
- Own task orchestration.
- Launch Lightroom Classic automatically; lifecycle management is a later Agent-side task.
- Require the user to select a Lightroom photo as the primary workflow.
- Use `selected photo`, `getTargetPhoto`, or `Run Tonevyra Correction` as the main product path.

Debug-only menu items are allowed only when they process existing bridge requests. Debug menus must not become the product workflow.

The formal product path is automatic bridge request processing inside the Lightroom plugin: the Agent writes an apply request JSON, the plugin automatically checks `runtime\bridge\lightroom_apply_requests`, applies the request, and writes a result JSON.

## Apply Request Contract

A valid apply request must contain at least:

```json
{
  "schema_version": "1.0",
  "request_id": "lr_apply_001",
  "task_id": "task_001",
  "source_path": "F:\\tonevyra_ai_agent\\runtime\\input\\test.jpg",
  "operation": "apply_develop_settings",
  "develop_settings": {
    "Exposure": 0.3,
    "Contrast": 10,
    "Highlights": -20,
    "Shadows": 15,
    "Vibrance": 8
  },
  "created_at": "2026-06-18T12:00:00Z"
}
```

`source_path` is how Lightroom knows which image to adopt. The plugin must find/import that path into the catalog and apply corrections to the resulting `LrPhoto`.

## Apply Result Contract

A successful result must contain at least:

```json
{
  "schema_version": "1.0",
  "request_id": "lr_apply_001",
  "task_id": "task_001",
  "source_path": "F:\\tonevyra_ai_agent\\runtime\\input\\test.jpg",
  "status": "applied",
  "catalog_action": "imported",
  "applied_parameters": {
    "Exposure": 0.3,
    "Contrast": 10,
    "Highlights": -20,
    "Shadows": 15,
    "Vibrance": 8
  },
  "error_code": null,
  "message": "Applied successfully",
  "completed_at": "2026-06-18T12:00:05Z"
}
```

A failure result must use `status: failed`, include `error_code`, include a clear `message`, mark recoverability where available, and must not silently discard the request.

## Acceptance Criteria

T-019 passes only when:

1. The plugin loads in Lightroom Classic.
2. The plugin reads bridge apply requests, not the input folder.
3. The plugin can process one request containing `source_path`.
4. The plugin can find/import the image in the Lightroom catalog.
5. The plugin applies Develop settings or a preset.
6. The plugin writes an apply result JSON.
7. The plugin does not own AI analysis, quality gate, DB decisions, or folder watching.
8. Existing fake worker and existing general harnesses are preserved.

## Implementation Guidance

Implement plugin-side automatic bridge request processing as the formal T-019 path. The plugin should poll/check `runtime\bridge\lightroom_apply_requests`, process Agent-created requests, and write result JSON files under `runtime\bridge\lightroom_apply_results`.

A manual/debug menu action such as `Tonevyra Diagnostics Process Pending Apply Request` may remain only as a diagnostic tool for troubleshooting an existing bridge request. It is not the normal product workflow, must not require selected-photo targeting, and must not replace the automatic bridge request path.

Automatic Lightroom launch, user folder selection UI, and full Agent lifecycle management remain outside T-019.
