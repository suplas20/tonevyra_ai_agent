# Vision Analysis Skill

## Purpose
Analyze only a 1024px sRGB JPEG preview plus metadata and return schema-validated visual diagnosis.

Vision analysis diagnoses the photo. It does not choose final Lightroom settings.

## Rules
- Vision model diagnoses only.
- Vision model must not directly output final Lightroom settings.
- Use mock backend until the pipeline is stable.
- Real local model must be local-only and offline.
- Persist raw and structured model outputs.
- Validate schema before any downstream use.
- Low-confidence or schema-risk outputs should propagate review behavior through Correction Planner.
- Real backend must receive only local preview path + metadata, never original RAW.

## Required Artifacts
`vision_prompt.txt`, `vision_raw_response.json`, `vision_structured.json`.

## Failure
Invalid schema must fail with `MODEL_OUTPUT_INVALID`.

## Harness Validation
`harness/scripts/run_vision_mock_test.py`
