# T-022 Local Model Provider Pipeline Harness Contract

## Purpose

This contract verifies that T-022 connects a real local model runtime to the T-021 Provider interfaces without bypassing the Common Agent Core, Adjustment Planner, Quality Evaluator, state machine, or retry policy.

## Required Execution Path

```text
plan policy
→ ModelAnalysisProvider
→ local model runtime
→ raw runtime envelope
→ normalized T-021 analysis result
→ policy/confidence validation
→ Adjustment Planner
→ Lightroom apply/export
→ ModelQualityProvider
→ raw runtime envelope
→ normalized T-021 quality result
→ Quality Evaluator / State Manager
```

## Required Skills

```text
skills/local-model-analysis-provider/SKILL.md
skills/model-quality-evaluation-provider/SKILL.md
```

All 27 T-021 baseline skills must remain present.

## Local Model Contract

The configured model must:

- be located under an allowlisted local root;
- have a stable model ID and revision;
- have a verified checksum;
- use a local runtime backend;
- disable remote inference;
- disable runtime downloads;
- reject external image URLs;
- operate with network access unavailable.

A checksum mismatch, missing model, path escape, remote endpoint, or runtime download configuration is a technical failure.

## Plan Routing Contract

```text
free     → module/module, model loading forbidden
lite     → module/module, model loading forbidden
standard → model/model, model loading allowed
pro      → model/model, model loading allowed
```

Free/Lite execution evidence must show that the model runtime was not initialized.

Standard/Pro must not silently execute Module Provider. Fallback is permitted only when the plan explicitly enables it and the fallback event is persisted.

Default:

```text
allow_module_fallback=false
```

## Runtime Envelope Contract

Each model call must record:

```text
schema_version
request_id
job_id
attempt_id
operation
provider_type
model_id
model_revision
model_checksum
runtime_backend
runtime_version
device
dtype
quantization
started_at
completed_at
latency_ms
parse_status
confidence
raw_output_checksum
normalized_output
```

`operation` must be `analysis` or `quality`.

## Analysis Output Contract

`normalized_output` for analysis must conform to T-021 analysis requirements and must not contain direct Lightroom execution values.

Forbidden anywhere in model output:

```text
lightroom_adjustments
develop_settings
preset_path
execute_command
plugin_command
```

## Quality Output Contract

Quality evaluation must reference both source and export checksums and normalize to one of:

```text
APPROVED
RETRY_REQUIRED
SOURCE_LIMITED
TECHNICAL_FAILED
FINAL_FAILED
```

Rules:

- `RETRY_REQUIRED` requires a semantic strategy and must not contain Lightroom slider values.
- `SOURCE_LIMITED` requires explicit source evidence.
- `TECHNICAL_FAILED` must not contain fabricated quality scores.
- Quality status is finalized by the T-021 Quality Evaluator and State Manager.

## Retry Contract

The following counters are distinct:

```text
model_runtime_retry_count
quality_retry_count
```

A model runtime retry must not consume the photo quality retry budget. A Lightroom reprocessing attempt must not be counted as a model runtime retry.

## Fallback Contract

Controlled fallback requires:

```text
allow_module_fallback=true
requested_provider=model
executed_provider=module
fallback_reason
fallback_event_id
degraded_mode=true
```

When fallback is disabled, a model technical failure terminates as `TECHNICAL_FAILED`.

## Strict Runtime Evidence

Strict mode requires a runtime evidence JSON produced by an actual local model execution. It must include:

```text
network_disabled=true
runtime_download_used=false
remote_api_used=false
model_checksum_verified=true
analysis_runtime
quality_runtime
source_checksum
export_checksum
model_runtime_retry_count
quality_retry_count
```

The analysis and quality runtime entries must identify the actual model and contain successful parse status, timings, and normalized outputs.

## Regression Contract

T-022 verification must preserve and pass:

```text
T-019 Lightroom Apply Adapter
T-020 Lightroom Final Export Adapter
T-021 Dual-Mode Common Agent Core and Closed-Loop Quality Reprocessing
```
