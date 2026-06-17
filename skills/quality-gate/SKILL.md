# Quality Gate Skill

## Purpose
Evaluate exported image quality and decide final task status.

The quality gate is the only stage that finalizes normal processing into `PASS`, `REVIEW_REQUIRED`, or `FAILED`.

## Required Scores
`exposure_score`, `color_score`, `sharpness_score`, `noise_score`, `saturation_score`, `underwater_cast_score`, `overall_score`.

## Thresholds
- `PASS >= 85`
- `REVIEW_REQUIRED 70-84`
- `FAILED < 70`

## Sticky Review Rule
If correction planning or vision analysis marked `requires_review=true`, the quality gate must not finalize as `PASS` even when the numeric score is high. The best final status is `REVIEW_REQUIRED`.

## Required Artifact
`quality_detail.json`

## Rules
- Do not retry forever.
- Save `quality_results`.
- Update final task status.
- Store `quality_loop` evidence in task_events.
- If the export file is missing, use structured failure (`EXPORT_FILE_MISSING`) instead of guessing quality.
- Keep the scoring deterministic for mock/fake harness inputs.

## Harness Validation
`harness/scripts/run_quality_gate_test.py`
