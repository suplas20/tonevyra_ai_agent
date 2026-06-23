# CONTRACT_LIGHTROOM_EXPORT_ADAPTER

## Status

T-020 acceptance contract.

## Objective

After T-019 has applied Develop settings successfully, the Lightroom Classic plugin must automatically export the corrected catalog rendition to the requested file path and write a durable export result JSON.

## Formal Product Path

```text
valid T-019 apply result
→ Agent export request
→ plugin automatic bridge processing
→ Lightroom export
→ actual output file
→ export result JSON
→ Agent verification
→ EXPORT_DONE
```

Manual export UI or a diagnostic menu is not the formal product path.

## Required Paths

```text
runtime\bridge\lightroom_export_requests
runtime\bridge\lightroom_export_results
runtime\output\temp
```

## Request Fields

- `schema_version`
- `request_id`
- `task_id`
- `apply_request_id`
- `source_path`
- `export_path`
- `command`
- `export_settings`
- `created_at`

The command must be `EXPORT_CORRECTED_IMAGE`.

`source_path` is the original corrected Lightroom catalog photo path and must
not be limited to JPG/JPEG. T-020 must support RAW sources such as `.ARW`,
`.CR3`, `.CR2`, `.NEF`, and `.DNG`. The default MVP `export_path` remains a
JPEG file because the export rendition is `JPEG / quality 95 / sRGB`.

## Result Fields

- `schema_version`
- `request_id`
- `task_id`
- `apply_request_id`
- `source_path`
- `export_path`
- `status`
- `export_settings`
- `lightroom_result`
- `file_result`
- `error_code`
- `message`
- `completed_at`

## Success Contract

A successful T-020 result must satisfy all of the following:

```text
status = exported
lightroom_result.plugin_loaded = true
lightroom_result.worker_running = true
lightroom_result.source_photo_found = true
lightroom_result.export_started = true
lightroom_result.export_completed = true
file_result.exists = true
file_result.size_bytes > 0
actual export_path exists and is not source_path
```

## Failure Contract

Any claimed request must end with a durable result. Failure results must use `status=failed`, include `error_code`, include a clear message, and indicate recoverability where known.

The plugin must not remove the only durable request evidence before a success/failure result is safely written.

## Boundaries

### Plugin may

- Read export requests.
- Find the corrected catalog photo by source path.
- Start a Lightroom SDK export session.
- Observe rendition/export completion.
- Verify the expected file exists.
- Write export results.

### Plugin must not

- Watch the user input folder.
- Analyze photos.
- Generate correction values.
- Reapply or alter correction plans as part of export.
- Compute quality scores.
- Make PASS/REVIEW/FAILED decisions.
- Access PostgreSQL.
- Require selected-photo targeting for the product path.
- Require user menu interaction for normal export.
- Overwrite the source photo.

## Existing Error Codes

Use existing project error codes first:

- `LIGHTROOM_REQUEST_FAILED`
- `LIGHTROOM_RESPONSE_TIMEOUT`
- `LIGHTROOM_EXPORT_FAILED`
- `EXPORT_FILE_MISSING`
- `ARTIFACT_WRITE_FAILED`
- `DB_WRITE_FAILED`

## Harness Failure Conditions

T-020 fails if:

- export request/result fixtures are missing or invalid;
- plugin code has no export bridge request/result handling;
- the product flow is manual-only;
- output success is reported without file existence and non-zero size;
- source path and export path may be the same;
- source fixtures only prove JPG/JPEG behavior and do not cover RAW source input;
- plugin owns AI, correction planning, quality scoring, DB logic, or input watching;
- T-019 files are removed or its acceptance contract is weakened.

## Canonical Commands

```powershell
cd F:\tonevyra_ai_agent
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent
```

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin --strict
```
