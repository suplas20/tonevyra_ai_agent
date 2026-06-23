# Closed-Loop Quality Reprocessing Skill

## Purpose

Use this skill for T-021 post-export quality evaluation, failure classification, bounded retry, source limitation, and final approval.

The closed loop begins only after T-020 has proven that the corrected output file was exported successfully.

```text
EXPORTED
→ EVALUATING
→ APPROVED
   or RETRY_REQUIRED → new attempt
   or SOURCE_LIMITED
   or FINAL_FAILED
```

Technical execution failures exit to `TECHNICAL_FAILED` and must not be disguised as quality failures.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t021/T-021_Dual_Mode_Photo_Agent_Core_Work_Order.md
3. .docs/t021/T-021_Implementation_Specification.md
4. skills/closed-loop-quality-reprocessing/SKILL.md
5. skills/quality-gate/SKILL.md
6. skills/recovery-loop/SKILL.md
7. skills/lightroom-final-export-adapter/SKILL.md
8. skills/artifact-storage/SKILL.md
9. skills/testing-harness/SKILL.md
```

## Decision Classes

```text
APPROVED
RETRY_REQUIRED
SOURCE_LIMITED
TECHNICAL_FAILED
FINAL_FAILED
```

`RETRY_REQUIRED` is non-terminal. The other four are terminal unless a separate operator-driven recovery workflow is invoked.

## Entry Condition

Quality evaluation may begin only when all T-020 export evidence is valid:

```text
export result status = exported
output file exists
output file size > 0
output path differs from source path
artifact checksum/registration succeeds
```

## Quality Dimensions

At minimum evaluate:

```text
exposure
highlight retention
shadow detail
white balance
color cast
saturation
contrast
noise
sharpness
oversharpening
halo
source-to-output improvement
```

Model quality mode may add subject, skin, background separation, mood, and set consistency, but it must retain the common technical dimensions.

## Retry Rules

A retry requires all of the following:

1. current status is `RETRY_REQUIRED`
2. quality retry budget remains
3. reason codes identify an actionable defect
4. next strategy differs from the previous strategy
5. a new attempt id and request ids are generated
6. previous attempt artifacts are immutable
7. expected improvement is recorded
8. loop-progress guard permits another attempt

## Retry Budgets

```text
free: 1
lite: 2
standard: 2
pro: 3
t021_mvp: 2
```

Technical recovery attempts use a separate bounded budget and do not consume quality retry budget.

## Source Limited Rule

Use `SOURCE_LIMITED` only with durable evidence such as:

```text
severe focus failure
severe motion blur
irrecoverable clipping
insufficient source resolution/data
```

Do not use `SOURCE_LIMITED` merely because the current plan performed poorly.

## Loop-Progress Guard

Stop with `FINAL_FAILED` when:

```text
retry budget exhausted
score improvement remains below configured minimum
same strategy or plan delta repeats
same dominant reason persists without a new strategy
policy forbids further processing
```

## Compatibility

Before DB migration is complete, preserve legacy statuses and add T-021 semantic evidence in events/payloads:

```text
APPROVED → PASS
SOURCE_LIMITED / TECHNICAL_FAILED / FINAL_FAILED → FAILED + failure_class
RETRY_REQUIRED → non-terminal retry event
EXPORTED → EXPORT_DONE
EVALUATING → QUALITY_CHECK
```

## Evidence

Each attempt must preserve:

```text
analysis_result.json
adjustment_plan.json
apply request/result
export request/result
quality_evaluation.json
state_transition.json
retry_decision.json when applicable
```

## Forbidden Behavior

- unbounded retries
- overwriting previous attempt artifacts
- evaluating quality before export proof
- plugin-side quality decisions
- treating technical errors as low quality
- retrying source-limited images automatically
- reusing request ids across attempts
- setting APPROVED from a provider raw response without policy validation

## Acceptance Checklist

- legal state transitions only
- quality and technical failure separation
- plan-specific retry limits
- new plan delta for each retry
- source limitation evidence
- final failure on exhaustion/no progress
- immutable per-attempt artifacts
- T-020 export regression gate passes
