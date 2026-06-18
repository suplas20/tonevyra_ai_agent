# Harness Prompt - T-019 Lightroom Apply Adapter Role Correction

Validate and implement T-019 as a Lightroom Apply Adapter, not as a folder watcher.

The Agent owns input folder watching, image analysis, correction planning, quality gates, DB evidence, and apply request creation.

The Lightroom Classic plugin owns only:

1. Read bridge request JSON from `runtime\bridge\lightroom_apply_requests`.
2. Validate `request_id`, `task_id`, `source_path`, and correction payload.
3. Use `source_path` to find/import the photo in Lightroom catalog.
4. Apply Develop settings or a preset.
5. Write result JSON to `runtime\bridge\lightroom_apply_results`.

Reject implementations where the plugin watches `runtime\input`, creates correction plans, runs model inference, computes quality scores, or uses selected Lightroom photo as the primary product workflow.

Run:

```powershell
python .\harness\scripts\verify_lightroom_apply_adapter_role.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
```
