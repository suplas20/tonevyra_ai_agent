# Dual-Mode Agent Core Skill

## Purpose

Use this skill for T-021 Common Agent Core, Provider abstraction, plan policy, normalized analysis schema, and Module/Model Provider integration.

T-021 does not create two independent agents. It creates one Common Agent Core with replaceable providers.

```text
Common Agent Core
→ AnalysisProvider (module or model)
→ normalized analysis
→ Adjustment Planner
→ Lightroom apply/export
→ QualityProvider (module or model)
→ State Manager / Retry Controller
```

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t021/T-021_Dual_Mode_Photo_Agent_Core_Work_Order.md
3. .docs/t021/T-021_Implementation_Specification.md
4. skills/dual-mode-agent-core/SKILL.md
5. skills/closed-loop-quality-reprocessing/SKILL.md
6. skills/correction-planner/SKILL.md
7. skills/lightroom-apply-adapter/SKILL.md
8. skills/lightroom-final-export-adapter/SKILL.md
9. skills/artifact-storage/SKILL.md
10. skills/testing-harness/SKILL.md
```

## Core Rule

```text
Provider output is analysis evidence.
Adjustment Planner output is the Lightroom plan.
Plugin output is execution evidence.
Quality Evaluator output is the product decision.
```

Do not collapse these responsibilities.

## Provider Interfaces

Implement replaceable interfaces for:

```text
AnalysisProvider
QualityProvider
ProviderRegistry
PlanPolicy
```

Required provider identifiers:

```text
module
model
```

Provider-specific raw outputs must be normalized into a shared versioned schema before downstream use.

## Module Provider

Module Provider is the T-021 MVP implementation priority.

Required characteristics:

- no model inference cost
- deterministic for the same input/config/version
- local-only
- histogram/exposure/color/noise/sharpness/blur/basic face/EXIF analysis
- structured reason codes
- versioned thresholds
- suitable for Free/Lite plans

## Model Provider

Model Provider adds semantic scene/subject/portrait/mixed-light/mood analysis.

Mandatory restrictions:

- local-only model files
- no remote API fallback
- no runtime download
- no external URL images
- no direct Lightroom adjustment output
- no direct final quality decision bypass
- schema validation and confidence gate
- raw response and normalized response stored separately

## Plan Policy

Canonical default mapping:

```text
free     → module/module, max quality retry 1
lite     → module/module, max quality retry 2
standard → model/model, max quality retry 2
pro      → model/model, max quality retry 3
t021_mvp → module/module, max quality retry 2
```

Do not intentionally reduce free-plan correction quality. Differentiate plans through provider capability, throughput, retry depth, output options, and advanced features.

## Adjustment Boundary

Provider results must not contain or directly execute:

```text
lightroom_adjustments
develop_settings
preset_path
```

Allowed flow:

```text
provider result
→ schema validation
→ normalized analysis
→ Adjustment Planner
→ clamp/safety validation
→ correction plan
```

## Persistence and Evidence

Persist:

```text
provider type/version
config hash
input artifact checksums
normalized result checksum
planner version
attempt id/no
plan tier
```

Do not store image binaries or large raw model payloads as DB blobs.

## Failure Handling

Provider execution or schema failures are technical failures. They are not photo-quality failures.

Do not silently switch from Model Provider to Module Provider. Controlled fallback requires an explicit policy, event, and test; T-021 MVP default is no automatic fallback.

## Acceptance Checklist

- Common core imports provider interfaces, not concrete implementations.
- Module Provider passes deterministic fixtures.
- Model Provider fixture matches common schema.
- Forbidden direct adjustment fields are rejected.
- Free/Lite plans do not initialize a model.
- Standard/Pro provider selection is policy-driven.
- T-019/T-020 adapter behavior is unchanged.
- Harness records provider and plan evidence.
