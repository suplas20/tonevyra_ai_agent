# Quality Gate Skill

## Purpose
Evaluate exported image quality and decide final task status.

## Required Scores
`exposure_score`, `color_score`, `sharpness_score`, `noise_score`, `saturation_score`, `underwater_cast_score`, `overall_score`.

## Thresholds
- `PASS >= 85`
- `REVIEW_REQUIRED 70-84`
- `FAILED < 70`

## Required Artifact
`quality_detail.json`

## Rules
- Do not retry forever.
- Save `quality_results`.
- Update final task status.
