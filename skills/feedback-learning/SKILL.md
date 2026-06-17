# Feedback Learning Skill

## Purpose
Store user feedback and manual edit information for future local learning and planner calibration.

## Required Artifacts
`user_feedback.json`, `manual_edit_delta.json`, `training_sample_manifest.json`.

## Rules
- MVP stores learning-ready data only.
- Do not fine-tune automatically.
- Do not silently learn from user behavior.
- Do not upload feedback externally.
- Create learning_samples only for approved feedback.
