# Correction Planner Skill

## Purpose
Convert structured vision analysis into safe, clamped Lightroom adjustment plans.

This file is the short compatibility summary. The authoritative detailed rules live in `skills/correction-planning/SKILL.md`.

## Rules
- Planner owns final Lightroom adjustment values.
- Model output must not directly control Lightroom settings.
- Clamp all values to allowed ranges.
- Emit only supported Lightroom parameters.
- Low confidence should set review behavior when required.
- `requires_review=true` is sticky and must reach the quality gate.
- Planner must be deterministic for the same validated vision input + config.

## Required Artifact
`correction_plan.json`

## Failure
Planning failure uses `CORRECTION_PLAN_FAILED`.

## Harness Validation
`harness/scripts/run_correction_planner_test.py`
