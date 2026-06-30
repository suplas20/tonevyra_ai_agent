# T-029 Codex 실행 프롬프트

## 2026-06-29 Scope Update

Radial-gradient / `radial_template` fallback is excluded from T-029.

Implement native Lightroom mask execution only. If native Subject, People, Object, Sky, or Background masking does not detect the intended target, record `skip_local` or `review_required` evidence and do not create a radial substitute, generated XMP preset, brush/UI fallback, or silent global fallback.

Allowed strategies:

```text
native_ai
skip_local
review_required
```

Forbidden for T-029:

```text
radial_template
template_ref
template_path
preset_path
generated_radial_xmp
mouse_coordinates
```

아래 내용을 Codex CLI 작업 프롬프트로 사용한다.

```text
Read AGENTS.md first.
Then read CLAUDE.md.

Read these T-029 documents completely:
- .docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md
- .docs/t029/T-029_Implementation_Specification.md
- .docs/t029/T-029_Lightroom_Live_Test_Checklist.md
- .docs/t029/T-029_Seed_Radial_Preset_Preparation_Guide.md

Read the related existing contracts and skills:
- .docs/t023/T-023_Semantic_Subject_Analysis_Local_Adjustment_Work_Order.md
- .docs/t028/T-028_Production_Reliability_Agent_Operations_Work_Order.md
- skills/semantic-subject-analysis/SKILL.md
- skills/lightroom-local-adjustment-planning/SKILL.md
- skills/lightroom-radial-mask-execution/SKILL.md
- skills/radial-mask-template-library/SKILL.md
- skills/lightroom-apply-adapter/SKILL.md
- skills/lightroom-plugin-implementation/SKILL.md
- skills/lightroom-bridge/SKILL.md
- skills/recovery-error-handling/SKILL.md
- skills/testing-harness/SKILL.md
- harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md

Implement T-029 only.

Goal:
Extend the existing Tonevyra Lightroom Classic plugin and Agent bridge so a validated local mask plan can be executed automatically. When Subject, People, and Object detection do not identify a small secondary background target, the Mask Strategy Planner must select a deterministic pre-authored radial-mask template from a versioned local library and the plugin must apply it non-destructively.

Mandatory real case:
The supplied T-029 fixture is an underwater portrait. The large foreground diver is detected, but the small person near the upper-left background is not detected by Subject, People, or Object. The faded red garment on that background person requires local red recovery. The required automatic strategy is radial_template, not brush/UI automation.

First inspect the current repository:
1. Locate the actual Lightroom plugin path and current bridge dispatcher.
2. Locate the current T-019 apply request/result implementation.
3. Locate T-023 semantic/local planning models and current capability registry.
4. Locate T-028 idempotency/checkpoint/recovery implementation.
5. Reuse existing modules when responsibilities already exist. Do not create a parallel plugin, bridge, planner, or state machine.

PHASE 0 IS A HARD GATE:
Before implementing the template library, prove in the supported Lightroom Classic version that the existing plugin can automatically apply one human-validated radial-mask preset and that its geometry is retained on the target photo.

Phase 0 must prove:
- automatic plugin application without user drawing;
- radial center/size/feather persists;
- result JSON is written;
- replay of the same idempotency key does not duplicate the mask;
- existing user masks are preserved;
- failure can be rolled back or safely reported.

Allowed implementation path:
Use only supported Lightroom Classic plugin/develop/preset application mechanisms already available to the project and verified by a live test.

Forbidden:
- AutoHotkey
- pyautogui
- mouse or screen-coordinate automation
- direct Lightroom catalog database editing
- runtime modification of user sidecar XMP files
- unverified private Lightroom APIs
- model-generated plugin commands or preset paths

If Phase 0 cannot be proven, stop. Do not invent a workaround. Produce a blocked report with error code BLOCKED_RADIAL_PRESET_APPLICATION, the exact tested Lightroom/plugin versions, commands, logs, and reproduction steps.

After Phase 0 passes, implement:

A. Agent models and strategy planner
- normalized oriented image geometry in 0..1 coordinates;
- native_ai | radial_template | skip_local | review_required strategy;
- native detection evidence, including target_detected=false;
- deterministic radial template selection with fit evidence;
- bounded local adjustment plan;
- no Provider direct execution fields.

B. Versioned radial template library
- use a validated seed preset;
- build-time generator, never hand-edit hundreds of files;
- manifest with template ID, relative path, SHA-256, geometry, feather, size/aspect class, Lightroom version support, and seed signature;
- local manifest ID resolution only;
- reject path traversal, unknown IDs, version mismatch, and checksum mismatch;
- initial grid may use 5x7 positions, three size classes, three aspect classes, and one high-feather class, unless Phase 0 evidence requires a safer configuration;
- version all policy and library changes.

C. Bridge and plugin
- add or extend command APPLY_LIGHTROOM_MASK_PLAN;
- validate t029.mask_apply.request.v1;
- capability snapshot;
- pre/post Develop settings snapshots;
- Tonevyra-owned mask namespace;
- apply selected radial template;
- apply only bounded local adjustments;
- optional local Point Color only when runtime capability is proven;
- atomic result t029.mask_apply.result.v1;
- idempotent replay;
- rollback on partial failure;
- never modify user-created masks.

D. Quality evidence
- connect post-export evaluation to target color recovery and spill risk;
- record target_color_recovery_gain, background_color_spill, neutral/skin shift, highlight clipping delta, mask alignment, and naturalness;
- do not mark completion based only on plugin status=applied.

E. Tests and harness
- make the provided T-029 static harness pass;
- add unit tests for geometry, fit, deterministic tie-break, clamp, native failure to radial fallback, unknown/checksum mismatch, replay, and rollback;
- add fake runtime evidence;
- run the real Lightroom checklist on the supplied image;
- run all T-019 through T-028 regression verifiers and existing project tests.

Use the existing source image fixture:
- harness/fixtures/images/t029_background_person_red_recovery.jpg

Required T-029 harness commands:
- python harness/scripts/verify_t029_lightroom_radial_masking.py --project-root .
- python harness/scripts/run_t029_radial_masking_runtime.py --project-root . --output runtime/t029_runtime_evidence.json --regressions-passed
- python harness/scripts/verify_t029_lightroom_radial_masking.py --project-root . --runtime-evidence runtime/t029_runtime_evidence.json

Strict real-Lightroom validation:
- python harness/scripts/verify_t029_lightroom_radial_masking.py --project-root . --runtime-evidence <runtime-evidence.json> --live-evidence <live-evidence.json> --strict

Do not add a new top-level job state for T-029.
Do not change model security/offline policy.
Do not remove or rename existing files, skills, fixtures, contracts, or verifiers.
Do not implement brush automation, object rectangle automation, segmentation bitmap import, model fine-tuning, dashboard work, or a new worker pool.

Completion requires:
1. Phase 0 live proof.
2. Valid request/result/capability/template schemas.
3. Deterministic radial fallback for the provided native-detection-failure case.
4. Plugin-created radial mask at the intended upper-left background target.
5. Bounded local red recovery with no unacceptable red spill.
6. Replay without duplicate masks.
7. User masks preserved and rollback evidence.
8. T-029 static, runtime, strict live, and T-019..T-028 regression gates pass.

After T-029 is complete, stop immediately. Do not begin another ticket.

Final report format:
Ticket ID:
Implemented scope:
Changed files:
Phase 0 result:
Supported Lightroom Classic version:
Plugin version:
Template library version and manifest SHA-256:
Commands run:
Static harness result:
Runtime harness result:
Strict live Lightroom result:
T-019..T-028 regression results:
Background-person red recovery result:
Idempotency result:
User-mask preservation/rollback result:
Known limitations:
Out-of-scope items not implemented:
Blocked items:
Waiting for user approval:
```
