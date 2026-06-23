# SaaS Plan Routing Skill

## Purpose

Use this skill for T-027 versioned Plan Policy selection and enforcement of Provider, retries, batch, resolution, output capability, priority, and fallback rules.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t027/T-027_SaaS_Plan_Routing_Usage_Cost_Control_Work_Order.md
3. skills/saas-plan-routing/SKILL.md
4. skills/usage-cost-control/SKILL.md
5. skills/dual-mode-agent-core/SKILL.md
6. skills/local-model-analysis-provider/SKILL.md
7. skills/testing-harness/SKILL.md
```

## Single Policy Entry Point

Do not scatter plan checks across components. Resolve an immutable policy snapshot at job start and pass the snapshot or policy reference through the pipeline.

## Quality Rule

Do not deliberately degrade Free/Lite correction quality. Plan differences come from capability, throughput, retry depth, batch, output features, and priority.

## Provider Rule

Free/Lite must not initialize model runtime. Standard/Pro model failures do not silently fall back unless the snapshot explicitly allows controlled fallback with full evidence.

## Client Trust Boundary

Never trust a client-provided plan identifier without validating the authenticated/local user scope against the active policy registry.

## Acceptance Checklist

- policy snapshot is immutable per job;
- routing is deterministic;
- free/lite model initialization is absent;
- fallback is explicit;
- quality degradation flags are rejected;
- all overrides are audited.
