# T-021 Implementation Prompt

Implement T-021 from the existing T-020 baseline.

Required order:

1. Read `AGENTS.md` and `CLAUDE.md`.
2. Read both T-021 documents.
3. Read both T-021 skills.
4. Preserve all T-019/T-020 files and regression behavior.
5. Build Common Agent Core interfaces.
6. Complete ModuleAnalysisProvider and ModuleQualityProvider first.
7. Add state machine, failure classification, and bounded retry.
8. Keep Model Provider behind an interface and common schema.
9. Do not let Provider output bypass Adjustment Planner.
10. Do not let Lightroom Plugin make quality decisions.
11. Run T-019, T-020, and T-021 harnesses.

Do not create a second repository, remote API fallback, unbounded loop, or free-plan quality sabotage.
