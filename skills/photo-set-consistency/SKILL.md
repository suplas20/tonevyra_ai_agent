# Photo Set Consistency Skill

## Purpose

Use this skill for T-024 grouping related photos, selecting representative images, extracting set baselines, detecting outliers, and maintaining visual consistency without damaging per-photo quality.

## Core Rule

Set consistency is a constraint and comparison target, not a command to copy identical settings to every photo.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t024/T-024_Batch_Processing_Photo_Set_Consistency_Work_Order.md
3. skills/photo-set-consistency/SKILL.md
4. skills/batch-photo-processing/SKILL.md
5. skills/semantic-subject-analysis/SKILL.md
6. skills/closed-loop-quality-reprocessing/SKILL.md
7. skills/testing-harness/SKILL.md
```

## Grouping Evidence

Use capture time, metadata, scene/lighting similarity, subject continuity, and user grouping. Store grouping confidence and reasons. Low-confidence images may remain separate or become outliers.

## Representative Selection

Choose representative images by technical quality, absence of source limitations, subject relevance, and median-like scene characteristics. Selection must be deterministic for the same dataset/config/version.

## Consistency Dimensions

```text
exposure
white balance
color cast
contrast
skin tone
subject emphasis
style intent
```

Keep per-photo quality scores separate from consistency scores.

## Outlier Rule

Do not force night, flash, backlit, or intentionally different frames to the set median. Persist outlier reason and individual handling policy.

## Acceptance Checklist

- grouping and representative selection are traceable;
- baseline uses ranges/deltas, not copied absolute settings;
- outliers are protected;
- per-photo quality remains primary;
- set retry does not create unbounded item retries.
