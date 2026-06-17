# Vision Analysis Skill

## Purpose
Analyze only a 1024px sRGB JPEG preview plus metadata and return schema-validated visual diagnosis.

## Rules
- Vision model diagnoses only.
- Vision model must not directly output final Lightroom settings.
- Use mock backend until the pipeline is stable.
- Real local model must be local-only and offline.
- Persist raw and structured model outputs.

## Required Artifacts
`vision_prompt.txt`, `vision_raw_response.json`, `vision_structured.json`.

## Failure
Invalid schema must fail with `MODEL_OUTPUT_INVALID`.
