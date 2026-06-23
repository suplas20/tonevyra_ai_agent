# User Style Profile Skill

## Purpose

Use this skill for T-025 creation, versioning, activation, rollback, opt-out, and local isolation of structured user style preferences.

## Required Reading Order

```text
1. AGENTS.md
2. .docs/t025/T-025_User_Style_Profile_Personalization_Work_Order.md
3. skills/user-style-profile/SKILL.md
4. skills/personalization-feedback-policy/SKILL.md
5. skills/correction-planner/SKILL.md
6. skills/feedback-learning/SKILL.md
7. skills/testing-harness/SKILL.md
```

## Profile Boundary

A style profile is high-level preference evidence. It must not contain executable Plugin commands, direct Develop settings, or arbitrary preset paths.

## Versioning

```text
DRAFT → ACTIVE → SUPERSEDED | DISABLED
```

Only one active profile per user scope. Updates create new versions; historical versions remain immutable and rollbackable.

## Initial Preference Dimensions

Exposure bias, contrast, highlight rolloff, shadow openness, WB bias, saturation/vibrance, skin warmth, skin smoothing, texture/clarity balance, sharpening, noise reduction, and mood tags.

## Priority

Technical safety and source limitations override user style. Set consistency and semantic intent are combined by the Planner using explicit versioned priority rules.

## Privacy

Profiles and evidence stay local, are isolated by user scope, and are not used across users. Opt-out prevents loading and applying the profile.

## Acceptance Checklist

- profile schema/version is valid;
- direct execution fields are rejected;
- one active profile per user scope;
- rollback is reproducible;
- opt-out disables application;
- cross-user access is blocked.
