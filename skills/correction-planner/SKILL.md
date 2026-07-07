# Correction Planner Skill

## Purpose
Convert structured vision analysis into safe, clamped Lightroom adjustment plans.

## Rules
- Planner owns final Lightroom adjustment values.
- Model output must not directly control Lightroom settings.
- Clamp all values to allowed ranges.
- Emit only supported Lightroom parameters.
- Low confidence should set review behavior when required.

## Planner modes (`TONEVYRA_PLANNER_MODE`)
Two interchangeable planners share the same `CorrectionPlan` output contract,
the `CORRECTION_PLAN` stage, and the `CORRECTION_PLAN_FAILED` error. No new
status/enum/error values are introduced.

- `legacy` (default): rule-based token mapping in `create_correction_plan()`.
  Maps categorical model issues to fixed adjustment values. Kept unchanged.
- `target_based`: measurement-driven planner in
  `correction/target_based/`. Requires the preview artifact. If the preview is
  missing or unreadable it degrades to `legacy` and forces `requires_review`.

### target_based 10-stage pipeline
1. `measurement.py` – quantitative measurement of the preview (luma, clipping,
   channel balance, per-hue saturation/coverage, sharpness, noise).
2. `engine._reconcile` – integrate model categorical/numeric output with measures.
3. `targets.build_target_state` – scene target envelope. The saturation floor is
   derived from the image's own measured chroma so a colorful photo is never
   pushed toward monochrome.
4. global = engine, local = legacy `_build_local_adjustments` (LocalAdjustmentPlanner).
5. `candidates.generate_candidates` – conservative/balanced/aggressive/model-anchored.
6. `constraints` – clamp to `ADJUSTMENT_RANGES` + monochrome guard + clipping guard.
7. `engine._score_candidate` – simulate each candidate, score distance to target.
8. `simulation.predict_measurement` – re-measure the predicted result.
9. `engine._secondary_correction` – single bounded second pass on residual error.
10. `PlannerDecisionLog` – full evidence, saved as `correction_decision_log.json`.

Simulation output is a PREDICTION, not a real Lightroom render. Ground truth is
the actual Lightroom export scored by the Quality Gate; the decision log records
`predicted_not_actual=true`.

## Required Artifact
`correction_plan.json`
(`target_based` also writes `correction_decision_log.json`;
`legacy` also writes `model_planner_comparison_log.json`.)

## Failure
Planning failure uses `CORRECTION_PLAN_FAILED`.

## T-032 Deployment Boundary

Production Planner rule execution moves to `tonevyra_planner_service`. The local Agent keeps the CorrectionPlan contract and independent range validation, but its production distribution must not contain Planner rules or a selectable local fallback. Existing local Planner implementations may remain only in server code, migration tooling, or explicitly test-only fixtures.
