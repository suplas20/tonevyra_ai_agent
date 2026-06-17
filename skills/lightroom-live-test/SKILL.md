# Folder-Driven Lightroom Live Test Skill

## Purpose

Use this skill when validating Tonevyra AI inside an actual installed Lightroom Classic environment.

This skill bridges automated harness tests and manual Lightroom validation while preserving the project concept: the user adds photos to an input folder; Tonevyra agent and Lightroom plugin process them automatically.

## Scope

Use this skill for:

- Loading `TonevyraAI.lrplugin` in Lightroom Classic
- Verifying worker running status
- Dropping a test photo into the input folder
- Confirming folder watcher task creation
- Confirming apply request/result files
- Confirming Develop setting application
- Capturing live evidence JSON
- Recording failures in a reproducible way

## Required manual test

Minimum live test:

1. Open Lightroom Classic.
2. Add `TonevyraAI.lrplugin` via Plug-in Manager.
3. Confirm plugin status is installed/running.
4. Confirm bridge worker is running.
5. Do not select a photo as the workflow trigger.
6. Copy one test photo into the configured input folder.
7. Confirm folder watcher created a task.
8. Confirm agent wrote Lightroom apply request JSON.
9. Confirm plugin wrote apply result JSON.
10. Confirm at least one Develop setting changed in Lightroom.
11. Run existing automated harness after the change.

## Evidence file

The apply result or live evidence JSON must include:

```json
{
  "schema_version": "t019.lightroom_apply.result.v1",
  "request_id": "...",
  "request_origin": "lightroom_plugin",
  "command": "APPLY_LIGHTROOM_SETTINGS",
  "task_id": "...",
  "status": "applied",
  "source_path": "...",
  "lightroom_result": {
    "plugin_loaded": true,
    "worker_running": true,
    "source_photo_found": true,
    "source_photo_imported": false,
    "develop_settings_applied": true
  },
  "applied_settings": {},
  "skipped_settings": {},
  "operator_notes": "Folder-driven live test passed."
}
```

## Required failure tests

Where feasible, run at least two of these:

- Lightroom plugin not running
- Apply request timeout
- Invalid apply request schema
- Unsupported parameter included
- Source path missing
- Catalog import failed

## Completion rule

A live test is not complete until the evidence JSON passes:

```bash
python harness/scripts/verify_lightroom_live_test_evidence.py --evidence <path>
```
