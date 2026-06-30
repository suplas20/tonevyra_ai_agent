# Harness Fixtures

이 폴더에는 하네스에서 사용하는 더미 입력/출력 fixture가 들어 있습니다.

## 원칙

- 실제 고객 사진을 저장하지 않습니다.
- private RAW/JPG는 Git에 올리지 않습니다.
- 모델 raw response fixture는 민감 데이터 없이 synthetic JSON만 사용합니다.

## 구성

```text
images/
  sample_underwater_01.jpg
vision_outputs/
  underwater_valid.json
  low_confidence.json
  invalid_schema.json
lightroom_responses/
  success_response.json
  export_failed_response.json
```


## T-020 Lightroom Final Export Adapter Fixtures

```text
lightroom_export_adapter/valid_export_request.json
lightroom_export_adapter/valid_export_result.json
lightroom_export_adapter/failed_export_result.json
lightroom_export_adapter/invalid_missing_export_path_request.json
```

These fixtures validate export request/result fields, output-file success semantics, failure evidence, and source/export path separation.

## T-029 radial masking fixtures

`harness/fixtures/t029_radial_masking/` covers the native-target-detection failure to deterministic radial-template fallback path, geometry validation, bounded adjustments, manifest integrity, idempotent replay, and rollback/user-mask preservation.

The source photo is stored at:

```text
harness/fixtures/images/t029_background_person_red_recovery.jpg
```

This image is a local test fixture and must not be uploaded or sent to an external model/service by the harness.

## T-030 Background/Tray Fixtures

`harness/fixtures/t030_background_tray/` covers partial-file stability, filesystem event coalescing, pause/resume, single instance, Worker crash recovery, tray state mapping, graceful shutdown, recursive output rejection, source safety, and Windows live-evidence template.
