# Lightroom Local Adjustment Planning Skill

## Purpose

Use this skill for T-023 conversion of semantic region intents into supported, bounded, conflict-resolved Lightroom local adjustment plans.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t023/T-023_Semantic_Subject_Analysis_Local_Adjustment_Work_Order.md
3. skills/lightroom-local-adjustment-planning/SKILL.md
4. skills/semantic-subject-analysis/SKILL.md
5. skills/correction-planner/SKILL.md
6. skills/lightroom-apply-adapter/SKILL.md
7. skills/lightroom-bridge/SKILL.md
8. skills/testing-harness/SKILL.md
```

## Planner-Only Rule

Only the Local Adjustment Planner may create executable local adjustment plans. Provider output is advisory evidence.

```text
semantic intent
→ capability check
→ bounded mapping
→ global/local conflict resolution
→ local plan
→ Apply Adapter
```

## Capability Registry

Every mask type and parameter must be declared as supported by the active Lightroom/Plugin capability snapshot. Unsupported features must be rejected or handled as explicit global-only degraded mode.

## Safety Rules

- clamp all exposure/color/texture/sharpening deltas;
- protect skin naturalness and face highlights;
- prevent strong positive texture/clarity on skin by default;
- prevent overlapping masks from stacking uncontrolled deltas;
- preserve global technical safety constraints;
- do not simulate a failed mask by applying the same delta globally.

## Conflict Resolution

Resolve conflicts deterministically using versioned priority rules. Persist the winning intent, suppressed intent, reason, and final bounded delta.

## Fallback

```text
mask unavailable or invalid
→ local plan not executed
→ fallback policy evaluated
→ global-only plan or TECHNICAL_FAILED
→ degraded_mode evidence
```

Fallback must not be silent.

## Attempt Evidence

Persist capability snapshot, semantic region version, local plan, conflict resolution, apply result, and per-region quality result. Previous attempts are immutable.

## Acceptance Checklist

- unsupported mask types fail validation;
- local plan references existing normalized regions;
- all values are bounded;
- conflict resolution is deterministic;
- global-only fallback is explicit;
- Plugin remains an executor, not a semantic planner.

## T-029 Radial Fallback Link

Superseded by 2026-06-29 scope update: T-029 radial fallback is excluded.

When Subject, People, Object, Sky, or Background does not detect the intended region, mark local execution as unsupported for that target and choose explicit `skip_local` or `review_required`. Do not evaluate radial fallback, do not select a template, and do not apply a silent global substitute.
