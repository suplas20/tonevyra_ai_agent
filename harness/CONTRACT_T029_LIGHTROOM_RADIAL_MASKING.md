# T-029 Lightroom Native Mask Execution Harness Contract

## Scope Update

As of 2026-06-29, radial-gradient / radial-template fallback is excluded from T-029.

This contract intentionally keeps the existing filename for compatibility with the already-added harness package, but the authoritative behavior is now native-mask-only:

- `radial_template` is not an allowed executable strategy.
- Radial preset seed files, generated radial template libraries, fit scoring, and manifest-based template resolution are out of scope.
- If the intended target is not detected by native Lightroom mask types, the Planner must choose `skip_local` or `review_required`.
- Silent global fallback is forbidden.

## Required Files

```text
.docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md
.docs/t029/T-029_Implementation_Specification.md
.docs/t029/T-029_Codex_Prompt.md
.docs/t029/T-029_Lightroom_Live_Test_Checklist.md
skills/lightroom-radial-mask-execution/SKILL.md
skills/radial-mask-template-library/SKILL.md
skills/T029_SKILL_INVENTORY.json
harness/schemas/t029_mask_apply_request.schema.json
harness/schemas/t029_mask_apply_result.schema.json
harness/schemas/t029_runtime_evidence.schema.json
harness/schemas/t029_live_evidence.schema.json
harness/fixtures/t029_radial_masking/
harness/scripts/verify_t029_lightroom_radial_masking.py
harness/scripts/run_t029_radial_masking_runtime.py
```

## Contract

- Provider output is semantic/color evidence only and cannot contain Plugin commands, template paths, preset paths, or final Lightroom values.
- Planner owns strategy, native target-detection evidence, bounded values, and explicit fallback.
- Plugin owns validated technical execution only.
- Native AI availability is not proof that the intended target was detected.
- Native target detection failure must select `skip_local` or `review_required`; it must not select `radial_template`.
- Geometry uses oriented normalized image coordinates in `0..1` as evidence, not as permission to synthesize a radial mask.
- Existing user masks must be preserved.
- Same idempotency key must not create a duplicate mask.
- UI/mouse automation, catalog DB modification, arbitrary runtime XMP mutation, radial fallback, and generated radial presets are forbidden.
- Strict completion requires real Lightroom native-mask execution evidence, export evidence, target/spill quality evidence, idempotency evidence, and user-mask preservation evidence.
- T-019 through T-028 regressions remain mandatory.

## Runtime Evidence

```text
schema_version = t029.runtime.evidence.v1
ticket = T029
completed = true
selected_strategy = review_required | skip_local | native_ai
native_detection_failed_safely = true when selected_strategy is review_required or skip_local
native_target_detected = true when selected_strategy is native_ai
clamps_valid = true
idempotent_replay = true
user_masks_preserved = true
regressions_passed = true
```

## Live Evidence

```text
schema_version = t029.live.evidence.v1
ticket = T029
phase0_passed = true
lightroom_version
plugin_version
native_mask_command_supported = true
native_target_detected = true for native-mask application evidence
mask_applied_without_ui_drawing = true
target_alignment_passed = true
red_recovery_passed = true when native target is applied
background_spill_passed = true
idempotent_replay_passed = true
user_masks_preserved = true
rollback_verified = true
export_file_exists = true
quality_evidence_present = true
regressions_passed = true
```
