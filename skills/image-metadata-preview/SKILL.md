# Image Metadata and Preview Skill

## Purpose
Extract basic metadata and generate the model-safe preview image.

This stage creates the only image input the vision model may use during MVP runtime.

## Rules
- Model must never receive the original RAW directly.
- Create a 1024px long-edge sRGB JPEG preview.
- Store `exif.json`.
- Store `preview_1024.jpg`.
- Register both artifacts in `task_artifacts`.
- Preview generation failure must be structured and recoverable.

## Do Not
- Do not run vision inference here.
- Do not create Lightroom corrections here.
- Do not send images to remote services.

## Harness Validation
`harness/scripts/run_metadata_preview_test.py`
