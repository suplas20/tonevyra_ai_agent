# T-023 Semantic Subject Analysis and Local Adjustment Harness Contract

## Required Files

```text
skills/semantic-subject-analysis/SKILL.md
skills/lightroom-local-adjustment-planning/SKILL.md
harness/schemas/t023_semantic_analysis.schema.json
harness/schemas/t023_local_adjustment_plan.schema.json
harness/fixtures/t023_semantic_local_adjustment/
harness/scripts/verify_t023_semantic_local_adjustment.py
```

## Contract

- Provider produces semantic evidence only.
- Local Adjustment Planner is the only executable local-plan creator.
- Region IDs, types, hierarchy, confidence, and source are traceable.
- Unsupported mask types fail or use explicit global-only degraded mode.
- Global/local conflict resolution is deterministic and bounded.
- Direct Plugin/mask execution fields are forbidden in Provider output.
- Strict evidence includes real Lightroom local apply/export proof and per-region quality result.
- T-019 through T-022 regressions remain mandatory.
