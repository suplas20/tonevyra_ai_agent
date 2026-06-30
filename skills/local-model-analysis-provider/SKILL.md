# Local Model Analysis Provider Skill

## Purpose

Use this skill to implement T-022 `ModelAnalysisProvider` with a directly loaded local vision model while preserving the T-021 Common Agent Core and Adjustment Planner boundary.

```text
Plan Router
→ ModelAnalysisProvider
→ LocalVisionModelRuntime
→ raw model response
→ ModelOutputNormalizer
→ T-021 normalized analysis schema
→ policy/confidence validation
→ Adjustment Planner
```

The model is an analysis provider. It is not a Lightroom command generator.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t022/T-022_Model_Provider_Integration_Work_Order.md
3. skills/local-model-analysis-provider/SKILL.md
4. skills/dual-mode-agent-core/SKILL.md
5. skills/vision-analysis/SKILL.md
6. skills/local-model-security/SKILL.md
7. skills/qwen-backend/SKILL.md if present
8. skills/correction-planner/SKILL.md
9. skills/artifact-storage/SKILL.md
10. skills/testing-harness/SKILL.md
```

## Core Boundary

```text
Model output = structured visual evidence and correction intent
Adjustment Planner output = Lightroom parameter plan
Plugin output = execution result
```

Reject any model output containing direct execution or finalized Lightroom settings.

Forbidden top-level or nested intent fields include:

```text
lightroom_adjustments
develop_settings
preset_path
execute_command
plugin_command
```

A semantic recommendation such as `reduce warm skin cast` is allowed. A slider command such as `Temp=-12` is not.

## Local-Only Runtime

The Runtime must:

- load a pre-provisioned model from an allowlisted local directory;
- verify model identifier, revision, configuration hash, and file checksum;
- reject missing or modified model files;
- work with network access disabled;
- never call a remote inference API;
- never download weights at runtime;
- never fetch an image from an external URL;
- not emit image bytes or secrets to telemetry.

The model backend must be behind a runtime adapter. Do not bind Common Agent Core code directly to a specific Qwen class or model filename.

## Model Lifecycle

Implement explicit lifecycle states:

```text
UNINITIALIZED
→ VALIDATING_ARTIFACTS
→ LOADING
→ READY
→ INFERENCING
→ READY
→ UNLOADING
→ UNINITIALIZED
```

Failures transition to a technical error and include a stable reason code.

Required reason codes:

```text
MODEL_NOT_FOUND
MODEL_CHECKSUM_MISMATCH
MODEL_LOAD_FAILED
MODEL_OOM
MODEL_TIMEOUT
MODEL_INFERENCE_FAILED
MODEL_OUTPUT_PARSE_FAILED
MODEL_SCHEMA_INVALID
MODEL_LOW_CONFIDENCE
```

## Input Contract

Model analysis receives references and metadata, not arbitrary remote resources.

```text
job_id
attempt_id
source_artifact_path
preview_artifact_path
source_checksum
preview_checksum
EXIF/basic metadata
plan policy
previous attempt summary (optional)
```

Resolve paths under configured artifact roots and reject traversal or symlink escape.

## Runtime Envelope

Persist a versioned runtime envelope separate from normalized analysis.

Required fields:

```text
schema_version
request_id
job_id
attempt_id
provider_type=model
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
```

Do not store large raw image payloads in the database.

## Normalization

Normalize the model response into the T-021 analysis schema before the Planner sees it.

Required semantic content:

- scene and genre;
- subject hierarchy;
- portrait and skin-tone risks;
- mixed-light interpretation;
- highlight and shadow risks;
- color and mood findings;
- noise, blur, and sharpness risks;
- source limitation candidates;
- retry-specific failure interpretation when an earlier attempt exists.

The Normalizer must be deterministic for the same raw response and version.

## Confidence Gate

Never silently accept low-confidence output.

```text
confidence passes threshold
→ use normalized analysis

confidence fails threshold
→ configured model runtime retry
→ explicit module fallback when policy permits
→ otherwise TECHNICAL_FAILED
```

Model runtime retry count and photo quality retry count are separate counters.

## Plan Routing

Canonical rules:

```text
free/lite     → never initialize Model Runtime
standard/pro  → route to ModelAnalysisProvider when model policy is active
```

Do not silently downgrade Standard/Pro to Module Provider. Controlled fallback requires:

```text
allow_module_fallback=true
allowed fallback reason
fallback event
requested_provider=model
executed_provider=module
degraded_mode=true
```

Default automatic fallback is disabled.

## Evidence

Persist:

```text
model manifest checksum
runtime configuration hash
input artifact checksums
raw response checksum
normalized analysis checksum
normalizer version
confidence threshold and result
requested/executed provider
fallback reason when applicable
load and inference metrics
```

## Acceptance Checklist

- Existing Module Provider behavior is unchanged.
- Free/Lite paths do not load a model or reserve GPU memory.
- Standard/Pro selection is policy-driven.
- Model files are local, allowlisted, and checksum-verified.
- Network and runtime download are disabled.
- Raw output and normalized output are distinct artifacts.
- Direct Lightroom values or commands are rejected.
- T-021 analysis schema validation passes.
- Runtime retry and quality retry are not conflated.
- Real local model evidence can be verified in strict harness mode.

## T-031 backend and unload rule

Support explicit CUDA and MPS backends behind a common interface. CPU fallback must be opt-in and observable. Model unload is complete only after the inference process exits.
