# Personalization Feedback Policy Skill

## Purpose

Use this skill for T-025 user approval/rejection, manual-edit delta capture, calibration candidate generation, evidence thresholds, and anti-overfitting rules.

## Core Rule

Feedback collection is local, explicit, versioned, and bounded. It does not automatically fine-tune the vision model.

## Allowed Evidence

```text
explicit approval or rejection
user-adjusted style strength
manual Lightroom edit delta
profile direct edit
repeated preference pattern
```

## Forbidden Behavior

- hidden background learning;
- external upload;
- cross-user sample mixing;
- automatic model fine-tuning;
- activating a calibration from insufficient evidence;
- treating one rejection as a universal preference.

## Calibration Gate

A candidate requires minimum sample count, confidence, consistent direction, bounded magnitude, and no conflict with technical safety. Candidate activation is explicit or policy-controlled and always versioned.

## Audit Evidence

Persist feedback source, user scope, profile version, before/after plan, manual delta, candidate calculation, confidence, acceptance decision, and rollback link.

## Acceptance Checklist

- insufficient evidence is rejected;
- opt-out stops collection/application;
- candidate changes are bounded;
- no automatic fine-tuning path exists;
- all data remains local and user-isolated.
