# Correction Planner Skill

## Purpose
Convert structured vision analysis into safe, clamped Lightroom adjustment plans.

## Rules
- Planner owns final Lightroom adjustment values.
- Model output must not directly control Lightroom settings.
- Clamp all values to allowed ranges.
- Emit only supported Lightroom parameters.
- Low confidence should set review behavior when required.

## Required Artifact
`correction_plan.json`

## Failure
Planning failure uses `CORRECTION_PLAN_FAILED`.
