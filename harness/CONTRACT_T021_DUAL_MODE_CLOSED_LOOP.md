# T-021 Harness Contract — Dual-Mode Agent Core and Closed-Loop Quality Reprocessing

## 1. Purpose

This contract verifies the T-021 architecture without replacing T-019/T-020 contracts. The Agent owns analysis, plan selection, quality evaluation, retries, and final decisions. The Lightroom Plugin remains a technical execution adapter.

## 2. Preservation Gate

The following must remain present:

```text
25 T-020 skill directories
skills/lightroom-apply-adapter/SKILL.md
skills/lightroom-final-export-adapter/SKILL.md
harness/CONTRACT_LIGHTROOM_APPLY_ADAPTER.md
harness/CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md
harness/scripts/verify_lightroom_apply_adapter_role.py
harness/scripts/verify_lightroom_export_adapter.py
```

T-021 adds:

```text
skills/dual-mode-agent-core/SKILL.md
skills/closed-loop-quality-reprocessing/SKILL.md
```

Expected cumulative skill count: 27.

## 3. Provider Contract

Allowed provider types:

```text
module
model
```

Required normalized analysis fields:

```text
schema_version
job_id
attempt_id
provider_type
provider_version
scene
subjects
technical_findings
color_findings
quality_risks
confidence
created_at
```

Forbidden Provider output fields:

```text
lightroom_adjustments
develop_settings
preset_path
final_decision
```

Provider outputs may suggest intent and defects but cannot bypass the Adjustment Planner.

## 4. Plan Policy Contract

```text
free     = module/module, max_quality_retries 1
lite     = module/module, max_quality_retries 2
standard = model/model, max_quality_retries 2
pro      = model/model, max_quality_retries 3
t021_mvp = module/module, max_quality_retries 2
```

No plan may include intentional image-quality degradation.

## 5. State Contract

Allowed states:

```text
CREATED
ANALYZING
ADJUSTMENT_READY
LIGHTROOM_PROCESSING
EXPORTED
EVALUATING
RETRY_REQUIRED
APPROVED
SOURCE_LIMITED
TECHNICAL_FAILED
FINAL_FAILED
```

Terminal states:

```text
APPROVED
SOURCE_LIMITED
TECHNICAL_FAILED
FINAL_FAILED
```

Required legal transitions:

```text
CREATED → ANALYZING
ANALYZING → ADJUSTMENT_READY | TECHNICAL_FAILED
ADJUSTMENT_READY → LIGHTROOM_PROCESSING | TECHNICAL_FAILED
LIGHTROOM_PROCESSING → EXPORTED | TECHNICAL_FAILED
EXPORTED → EVALUATING | TECHNICAL_FAILED
EVALUATING → APPROVED | RETRY_REQUIRED | SOURCE_LIMITED | TECHNICAL_FAILED | FINAL_FAILED
RETRY_REQUIRED → ADJUSTMENT_READY | FINAL_FAILED
```

## 6. Export Entry Gate

`EXPORTED` requires all T-020 evidence:

```text
status=exported
output exists
output size > 0
source_path != export_path
artifact registration/checksum complete
```

Quality evaluation before this evidence is invalid.

## 7. Quality Result Contract

Required fields:

```text
schema_version
job_id
attempt_id
provider_type
status
scores
reason_codes
retry_recommendation
source_limit_evidence
created_at
```

Allowed status values:

```text
APPROVED
RETRY_REQUIRED
SOURCE_LIMITED
TECHNICAL_FAILED
FINAL_FAILED
```

## 8. Retry Contract

A quality retry must:

```text
increment attempt_no
create a new attempt_id
create new apply/export request ids
preserve previous artifacts
record reason codes and next strategy
respect plan retry budget
record plan delta and score delta
terminate when progress guard fails
```

Technical recovery budget is separate from quality retry budget.

## 9. Plugin Boundary Contract

The Plugin must not:

```text
run Module or Model Provider
calculate quality scores
choose a SaaS plan
set APPROVED/RETRY_REQUIRED/SOURCE_LIMITED/FINAL_FAILED
create retry plans
access PostgreSQL
```

## 10. Artifact Contract

Per attempt:

```text
attempt_manifest.json
analysis_result.json
normalized_analysis.json
adjustment_plan.json
lightroom_apply_request.json
lightroom_apply_result.json
lightroom_export_request.json
lightroom_export_result.json
quality_evaluation.json
state_transition.json
retry_decision.json when retrying
```

## 11. Compatibility Contract

Legacy states remain readable. Before full status migration:

```text
EXPORTED = EXPORT_DONE + t021 event evidence
EVALUATING = QUALITY_CHECK + t021 event evidence
APPROVED = PASS + t021_decision
other terminal failures = FAILED + failure_class
RETRY_REQUIRED = non-terminal event
```

## 12. Acceptance Command

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent
```

Runtime evidence mode:

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent --job-evidence <job-manifest.json> --strict
```
