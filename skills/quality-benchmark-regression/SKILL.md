# Quality Benchmark and Regression Skill

## Purpose

Use this skill for T-026 reproducible benchmark runs, provider/version comparison, metric aggregation, regression thresholds, and release gating.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t026/T-026_Quality_Benchmark_Regression_Work_Order.md
3. skills/quality-benchmark-regression/SKILL.md
4. skills/expert-reference-evaluation/SKILL.md
5. skills/model-benchmark-loop/SKILL.md
6. skills/quality-gate/SKILL.md
7. skills/testing-harness/SKILL.md
```

## Separation Rule

Production Quality Gate decides one job. Benchmark evaluates systems across a fixed dataset. Do not use production self-scores as the sole benchmark result.

## Dataset Integrity

Use versioned manifests with source/reference checksums, split, genre, difficulty, and license/consent. Detect train/calibration/test overlap.

## Fair Comparison

Provider/version comparisons require the same source, export settings, Lightroom version/config, benchmark policy, and metric version.

## Metrics

Aggregate technical, perceptual, human-review, approval/retry, latency, memory, throughput, and failure metrics by overall and genre strata.

## Regression Gate

Thresholds are versioned. A critical genre or safety regression can block release even when the overall average improves.

## Acceptance Checklist

- dataset version and split are valid;
- no test leakage;
- comparison conditions match;
- metrics are versioned;
- thresholds cannot change silently;
- release decision is machine-readable and traceable.
