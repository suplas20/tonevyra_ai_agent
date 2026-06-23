# Model Quality Evaluation Provider Skill

## Purpose

Use this skill to implement T-022 `ModelQualityProvider`, which compares the original source and Lightroom export, produces a normalized T-021 quality result, and supplies bounded retry reasoning without bypassing the Quality Evaluator or Adjustment Planner.

```text
source + export + applied plan + analysis
→ ModelQualityProvider
→ LocalVisionModelRuntime
→ raw quality response
→ quality normalizer
→ T-021 quality schema
→ Quality Evaluator / State Manager
→ APPROVED | RETRY_REQUIRED | SOURCE_LIMITED | TECHNICAL_FAILED | FINAL_FAILED
```

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t022/T-022_Model_Provider_Integration_Work_Order.md
3. skills/model-quality-evaluation-provider/SKILL.md
4. skills/closed-loop-quality-reprocessing/SKILL.md
5. skills/quality-gate/SKILL.md
6. skills/local-model-analysis-provider/SKILL.md
7. skills/correction-planner/SKILL.md
8. skills/lightroom-final-export-adapter/SKILL.md
9. skills/artifact-storage/SKILL.md
10. skills/testing-harness/SKILL.md
```

## Paired Evaluation Rule

The Provider must receive both source and export references. Evaluating only the export is insufficient because T-022 must judge improvement, damage, recoverability, and source limitations.

Required input:

```text
job_id
attempt_id
source_artifact_path
export_artifact_path
source_checksum
export_checksum
normalized analysis result
applied adjustment plan
previous quality result (optional)
plan policy
```

## Evaluation Dimensions

The model evaluates:

- exposure suitability;
- highlight preservation;
- shadow detail;
- white balance and color cast;
- saturation and contrast;
- noise and detail;
- oversharpening and halo risk;
- portrait skin naturalness;
- subject emphasis;
- subject/background separation;
- mood preservation;
- source-to-export improvement;
- retry potential;
- source limitation evidence.

## Output Boundary

Normalize model output into the T-021 quality schema.

Required fields:

```text
status
scores
reason_codes
improvement_summary
retry_recommendation
source_limit_evidence
confidence
```

The model status is a candidate. The Quality Evaluator and State Manager validate and finalize it.

Forbidden fields:

```text
lightroom_adjustments
develop_settings
preset_path
execute_command
plugin_command
force_state_transition
```

## Decision Requirements

### APPROVED

- scores and reason codes support approval;
- no unresolved blocking defect exists;
- source-to-export improvement is recorded.

### RETRY_REQUIRED

- retry remains within plan budget;
- a correctable failure is identified;
- `retry_recommendation.recommended=true`;
- the recommendation contains semantic strategy, priority, expected improvement, and constraints;
- it does not repeat an ineffective previous strategy without new evidence;
- it does not contain direct Lightroom values.

### SOURCE_LIMITED

- explicit source limitation evidence is present;
- the limitation is attributable to the source, not a model or plugin failure;
- examples include unrecoverable clipping, severe focus failure, severe motion blur, or insufficient source data.

### TECHNICAL_FAILED

- used for model/runtime/schema/plugin/file failures;
- must not include fabricated quality scores;
- does not consume a photo quality retry.

### FINAL_FAILED

- quality retry budget is exhausted or expected improvement is below policy threshold;
- the final reason references prior attempts.

## Retry Separation

Maintain separate counters:

```text
model_runtime_retry_count
quality_retry_count
```

A model timeout retry is not a Lightroom quality reprocessing attempt. A Lightroom reprocessing attempt is not a model runtime retry.

## Anti-Loop Rules

Before accepting `RETRY_REQUIRED`, compare against prior attempts:

```text
reason code overlap
strategy fingerprint
planner delta hash
quality score delta
expected improvement
```

Reject or terminate a retry when the same strategy is repeating without measurable improvement.

## Fallback

ModelQualityProvider failure does not automatically become ModuleQualityProvider execution.

Controlled fallback requires explicit plan policy and evidence:

```text
requested_provider=model
executed_provider=module
fallback_reason
fallback_event_id
degraded_mode=true
```

Default automatic fallback is disabled.

## Evidence

Persist:

```text
source/export checksums
model/runtime identity
raw quality response checksum
normalized quality checksum
quality schema validation
confidence gate result
status candidate and finalized status
retry strategy fingerprint
previous-attempt linkage
runtime metrics
fallback evidence when applicable
```

## Acceptance Checklist

- Source and export are always evaluated as a pair.
- T-021 quality schema validation passes.
- Model output cannot directly change Lightroom settings or state.
- `RETRY_REQUIRED` has structured semantic strategy.
- `SOURCE_LIMITED` has source evidence.
- `TECHNICAL_FAILED` has no fake quality scores.
- Runtime retries and quality retries are separated.
- Repeated ineffective retry strategies are detected.
- Plan retry budgets remain enforced by T-021 Retry Controller.
- Real export evaluation evidence can be verified in strict harness mode.
