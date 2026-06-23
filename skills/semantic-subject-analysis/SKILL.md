# Semantic Subject Analysis Skill

## Purpose

Use this skill for T-023 semantic region detection, primary-subject ranking, portrait/skin/sky/background interpretation, confidence gating, and normalized region evidence.

```text
source / preview
→ semantic analyzer
→ normalized regions
→ hierarchy / overlap / confidence validation
→ Local Adjustment Planner
```

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t023/T-023_Semantic_Subject_Analysis_Local_Adjustment_Work_Order.md
3. skills/semantic-subject-analysis/SKILL.md
4. skills/lightroom-local-adjustment-planning/SKILL.md
5. skills/local-model-analysis-provider/SKILL.md
6. skills/dual-mode-agent-core/SKILL.md
7. skills/testing-harness/SKILL.md
```

## Core Boundary

Semantic analysis produces evidence and intent. It does not generate executable Lightroom masks or final Develop values.

Forbidden output:

```text
plugin_command
execute_mask
lightroom_mask_payload
final_develop_settings
preset_path
force_state_transition
```

## Region Contract

Each region requires:

```text
region_id
region_type
priority
confidence
geometry_or_reference_intent
attributes
quality_risks
recommended_intents
source
```

Region IDs must remain stable inside one attempt. A new attempt may create a new region version but must link to the previous region when comparable.

## Allowed Initial Region Types

```text
primary_subject
secondary_subject
person
face
skin
hair
sky
background
foreground
product
object
```

Do not invent new region types without schema and harness updates.

## Confidence and Hierarchy

- low-confidence regions do not reach automatic local execution;
- face must be associated with a person when evidence exists;
- skin intent must not cover unrelated background colors;
- overlapping regions require parent/child or conflict evidence;
- primary-subject ranking must be deterministic for the same input/version.

## Retry Behavior

On quality retry, compare:

```text
region set fingerprint
primary subject
confidence deltas
reason-code deltas
previous local-plan result
```

Do not repeat identical semantic strategy without new evidence.

## Evidence

Persist raw provider output separately from normalized semantic regions, including provider/model version, prompt/config hash, input checksums, normalizer version, confidence gate, and rejected regions.

## Acceptance Checklist

- normalized region schema passes;
- direct execution fields are rejected;
- region hierarchy/overlap is valid;
- confidence gate blocks weak regions;
- source and provider evidence is traceable;
- T-021/T-022 provider boundaries remain intact.
