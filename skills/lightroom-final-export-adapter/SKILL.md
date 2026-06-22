# Lightroom Final Export Adapter Skill

## Purpose

Use this skill for T-020 Lightroom Final Export Adapter work.

T-019 applies Agent-created correction values to the Lightroom catalog photo. T-020 exports that corrected catalog rendition to an actual image file without requiring the user to operate Lightroom's export UI.

The formal product flow is:

```text
T-019 apply result: applied
→ Agent creates export request
→ Lightroom Plugin automatically processes export request
→ corrected image file is created
→ Plugin writes export result
→ Agent verifies file and records EXPORT_DONE
```

## Required Reading Order

```text
1. AGENTS.md
2. T-020_Lightroom_Final_Export_Adapter_Work_Order.md
3. skills/lightroom-apply-adapter/SKILL.md
4. skills/lightroom-final-export-adapter/SKILL.md
5. skills/lightroom-bridge/SKILL.md
6. skills/artifact-storage/SKILL.md
7. skills/recovery-error-handling/SKILL.md
8. skills/testing-harness/SKILL.md
```

The work-order document is the primary T-020 implementation instruction. This skill and the harness are supporting procedure and acceptance controls.

## Canonical Paths

```text
Project root: F:\tonevyra_ai_agent
Plugin: F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
Export requests: F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_requests
Export results: F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_results
Temporary output: F:\tonevyra_ai_agent\runtime\output\temp
```

## Preconditions

Create an export request only after a valid T-019 apply result proves that:

```text
status = applied
develop_settings_applied = true
catalog_action = imported or found_existing
source_photo_imported = true or source_photo_found = true
```

`LIGHTROOM_REQUESTED` alone is not an export precondition.

## Agent Responsibilities

1. Validate the T-019 apply result.
2. Generate normalized absolute `source_path` and `export_path` values.
3. Write the export request atomically.
4. Persist request evidence through Artifact Storage and DB/task events.
5. Collect the export result.
6. Verify the actual output file exists and has non-zero size.
7. Register checksum, size, MIME type, and artifact metadata.
8. Transition to `EXPORT_DONE` only after JSON and file verification.
9. Use bounded timeout, retry, and recovery logic.

## Plugin Responsibilities

1. Automatically check `lightroom_export_requests`.
2. Validate the request contract.
3. Locate the corrected catalog photo by `source_path`.
4. Export the current corrected Lightroom rendition using the requested settings.
5. Verify export completion and output existence.
6. Write one success or failure result for every claimed request.
7. Preserve requests or processing evidence until a durable result exists.

## Prohibited Behavior

The plugin must not:

- Watch `runtime\input`.
- Analyze image content.
- Generate or alter correction plans.
- Recalculate Develop settings.
- Compute quality scores.
- Access PostgreSQL.
- Use selected-photo/manual export as the formal product path.
- Require the user to press an export menu command.
- Overwrite the source image.
- Export outside the requested safe output root.
- Report success when no non-empty output file exists.

## MVP Export Profile

```text
format: JPEG
quality: 95
color_space: sRGB
resize: false
output_sharpening: screen / standard
overwrite: false
```

Other formats and multiple simultaneous presets are deferred.

## Request Contract

A valid T-020 request contains:

```text
schema_version
request_id
task_id
apply_request_id
source_path
export_path
command
export_settings
created_at
```

`command` must be `EXPORT_CORRECTED_IMAGE`.

## Result Contract

A valid result contains:

```text
schema_version
request_id
task_id
apply_request_id
source_path
export_path
status
export_settings
lightroom_result
file_result
error_code
message
completed_at
```

Success requires:

```text
status = exported
lightroom_result.export_completed = true
file_result.exists = true
file_result.size_bytes > 0
```

## Error Policy

Prefer the existing project error codes:

```text
LIGHTROOM_REQUEST_FAILED
LIGHTROOM_RESPONSE_TIMEOUT
LIGHTROOM_EXPORT_FAILED
EXPORT_FILE_MISSING
ARTIFACT_WRITE_FAILED
DB_WRITE_FAILED
```

Do not invent new error codes without updating project rules, enums, DB constraints, migrations, tests, fixtures, and recovery together.

## State Policy

Do not introduce a new T-020 task status.

```text
LIGHTROOM_PROCESSING
→ export request/result processing
→ verified file and result
→ EXPORT_DONE
→ QUALITY_CHECK
```

## Recovery Policy

Recovery must distinguish:

1. Request exists, result missing.
2. Result says exported, file missing.
3. File exists, result missing.
4. File and result exist, artifact/DB registration missing.
5. Duplicate request ID or repeated processing.

Logs are not the source of truth. Use request/result files, output existence, artifact records, checksums, and DB state.

## Acceptance Criteria

T-020 passes only when:

1. Export starts only after T-019 apply success.
2. The normal path is automatic bridge processing.
3. The corrected catalog rendition is exported to `export_path`.
4. The output file exists and is non-empty.
5. The source image is unchanged.
6. A result JSON is written for success and failure.
7. Agent verifies the result and file before `EXPORT_DONE`.
8. Existing T-019 behavior and all existing files are preserved.
9. Static harness, fixture validation, and live evidence validation pass.

## Canonical Harness Commands

```powershell
cd F:\tonevyra_ai_agent
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent
```

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py `
  --project-root F:\tonevyra_ai_agent `
  --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin `
  --strict
```

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py `
  --project-root F:\tonevyra_ai_agent `
  --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin `
  --result-json F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_results\<result>.json `
  --require-output-file `
  --strict
```
