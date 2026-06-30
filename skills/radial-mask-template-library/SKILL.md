# Radial Mask Template Library Guardrail Skill

## Purpose

Use this skill when T-029 work touches old radial-template files, fixtures, manifests, or verifier language.

Scope update, 2026-06-29: radial-gradient / radial-template fallback is excluded from T-029. This skill directory remains only to preserve the T-029 skill inventory count and to prevent accidental reintroduction of radial fallback.

## Core Rule

Do not build, generate, validate, select, or execute radial-mask templates for T-029.

## Forbidden In T-029

```text
validated seed radial preset
radial template generator
radial template manifest as runtime dependency
radial_template strategy
template_id selection
template_ref in mask requests
template_path or preset_path in Provider output
runtime radial XMP mutation
radial geometry fitting as automatic fallback
```

## Required Replacement Behavior

When native Subject, People, Object, Sky, or Background masks do not detect the intended target:

```text
target_detected=false
→ no mask apply request for that target
→ skip_local or review_required
→ persisted reason evidence
→ no silent global substitute
```

## Security And Integrity

- Reject model-supplied preset/template paths.
- Reject path traversal and arbitrary XMP paths.
- Keep old radial fixtures clearly marked as deprecated if retained for historical comparison.
- Do not download templates at runtime.

## Acceptance

- verifier rejects `radial_template` as an executable T-029 strategy;
- deterministic runtime evidence proves native-detection failure is handled safely;
- strict live evidence proves native mask execution only for detected targets;
- no radial fallback is presented as T-029 completion evidence.
