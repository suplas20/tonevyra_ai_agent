# Lightroom Native Mask Execution Skill

## Purpose

Use this skill for T-029 Plugin-side execution of validated Lightroom native mask plans.

Scope update, 2026-06-29: radial-gradient / radial-template fallback is excluded from T-029. This skill directory keeps its original name only for inventory compatibility. Do not implement radial fallback from this skill.

## Required Reading

```text
AGENTS.md
.docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md
.docs/t029/T-029_Implementation_Specification.md
skills/lightroom-local-adjustment-planning/SKILL.md
skills/lightroom-apply-adapter/SKILL.md
skills/lightroom-plugin-implementation/SKILL.md
skills/recovery-error-handling/SKILL.md
harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md
```

## Executor-Only Boundary

The Plugin executes a Planner-approved native mask operation. It does not infer the target, choose a fallback geometry, invent local values, or make a quality decision.

```text
validated request
→ native capability check
→ native target-detection evidence check
→ pre-apply snapshot
→ native mask apply
→ bounded values
→ result evidence
```

## Mandatory Rules

- Accept only `APPLY_LIGHTROOM_MASK_PLAN` requests with the T-029 schema.
- Execute only `native_ai` operations whose native assessment proves `target_detected=true`.
- Use the `Tonevyra::T029::` mask namespace.
- Preserve all user-created masks.
- Persist pre/post Develop settings snapshots.
- Treat replay of the same idempotency key as reuse/no-op, not a second mask.
- Roll back or fail safely on partial execution.
- Return explicit `skipped`, `failed`, `skip_local`, or `review_required` evidence when native capability or target detection is absent.

## Forbidden

```text
AI inference in Lua
semantic target selection in Lua
radial_template fallback
radial gradient preset application
template library lookup
mouse/UI automation
AutoHotkey or pyautogui
catalog DB modification
unverified private Lightroom APIs
runtime user sidecar overwrite
silent global fallback
```

## Local Color

Local Point Color may be used only when the runtime capability probe proves support. Otherwise apply a lower-strength bounded native correction or return `skip_local`/`review_required`. Never pretend unsupported color isolation succeeded.

## Acceptance

- real Lightroom native mask application passes;
- result and snapshots exist;
- replay does not duplicate;
- user masks remain unchanged;
- native target-detection failure becomes `skip_local` or `review_required`;
- strict T-029 harness passes.
