# Feedback Learning Skill

## Purpose
Store user feedback and manual edit information for future local learning and planner calibration.

MVP learning means local data capture and approval tracking. It does not mean live fine-tuning during normal runtime.

## Required Artifacts
`ai_settings.json`, `final_settings.json`, `manual_edit_delta.json`, `user_feedback.json`, `training_sample_manifest.json`.

## Required Tables
`feedback_records`, `learning_samples`.

Future extension placeholders, only when explicitly requested by a migration ticket:
`manual_edit_records`, `style_profiles`.

## Rules
- MVP stores learning-ready data only.
- Do not fine-tune automatically.
- Do not silently learn from user behavior.
- Do not upload feedback externally.
- Create `learning_samples` only for approved feedback.
- Rejected/unapproved feedback may be stored as feedback evidence but must not create learning samples.
- Store `feedback_loop` evidence in task_events.
- Manual edit delta is computed from AI-applied settings vs final/current settings.

## Acceptance Criteria
- Approved feedback creates one `feedback_records` row and one `learning_samples` row.
- Unapproved feedback creates no `learning_samples` row.
- Required artifacts exist and verify checksum.
- `harness/scripts/verify_feedback_learning.py` passes.
