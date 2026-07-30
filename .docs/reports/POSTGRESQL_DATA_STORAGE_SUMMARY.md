# Tonevyra AI Agent — PostgreSQL 저장 데이터 요약

## 목적

이 문서는 Tonevyra AI Agent가 PostgreSQL에 저장하는 데이터의 범위를 정리한다.

Tonevyra의 PostgreSQL은 이미지 파일 저장소가 아니라, 사진 처리 작업의 상태와 복구를 위한 운영 데이터베이스다.

```text
PostgreSQL:
작업 상태, stage, 이벤트, artifact 인덱스, 품질 점수, 피드백, 학습 후보 메타데이터 저장

로컬 파일시스템:
원본 사진, preview, export, model response, prompt, quality detail 등 실제 산출물 파일 저장
```

## 핵심 원칙

PostgreSQL에는 큰 바이너리 데이터를 저장하지 않는다.

저장하지 않는 대표 데이터:

```text
원본 RAW/JPG 이미지
1024px preview.jpg 바이너리
Lightroom export 이미지 바이너리
raw model response 전체 대용량 payload
vision prompt 전문
quality detail 대용량 파일
Lightroom request/response 파일 원본
```

이 데이터들은 로컬 artifact 파일로 저장하고, PostgreSQL에는 파일 경로, 크기, SHA-256 checksum, artifact type, version만 저장한다.

## 저장 테이블

### image_tasks

사진 1장에 대한 처리 작업의 source of truth다.

저장 데이터:

```text
id
source_path
source_hash
file_name
file_ext
file_size_bytes
status
current_stage
error_code
error_message
failed_stage
retry_count
overall_score
quality_decision
created_at
updated_at
completed_at
```

역할:

```text
작업 생성 여부
현재 처리 상태
현재 stage
실패 정보
재시도 횟수
최종 품질 결과
완료 시각
```

### task_artifacts

artifact 파일의 인덱스 테이블이다. 파일 본문은 저장하지 않는다.

저장 데이터:

```text
id
task_id
artifact_type
artifact_path
sha256
size_bytes
mime_type
version
created_at
```

예상 artifact type:

```text
EXIF_JSON
PREVIEW_JPEG
VISION_PROMPT
VISION_RAW_RESPONSE
VISION_STRUCTURED
CORRECTION_PLAN
LIGHTROOM_REQUEST
LIGHTROOM_RESPONSE
QUALITY_DETAIL
EXPORTED_IMAGE
RECOVERY_DECISION
AI_SETTINGS
FINAL_SETTINGS
MANUAL_EDIT_DELTA
FEEDBACK_RECORD
TRAINING_SAMPLE_MANIFEST
```

역할:

```text
artifact 파일 위치 추적
파일 무결성 확인
복구 시 필요한 산출물 존재 여부 판단
stage 완료 증거 보존
```

### task_events

작업 흐름에서 발생한 이벤트를 저장한다.

저장 데이터:

```text
id
task_id
event_type
stage
message
payload_json
created_at
```

역할:

```text
상태 전환 기록
loop event 기록
failure event 기록
recovery event 기록
human review event 기록
```

Loop 활동은 task status가 아니라 task event로 기록한다.

### stage_results

각 처리 stage의 요약과 실행 시간을 저장한다.

저장 데이터:

```text
id
task_id
stage
stage_status
summary_json
started_at
finished_at
duration_ms
created_at
```

역할:

```text
metadata stage 결과 요약
preview stage 결과 요약
vision stage 결과 요약
correction_plan stage 결과 요약
lightroom/export stage 결과 요약
quality stage 결과 요약
```

주의:

```text
stage_results.summary_json에는 요약만 저장한다.
큰 raw model output이나 debug log 전문을 저장하지 않는다.
```

### quality_results

품질 평가 결과를 저장한다.

저장 데이터:

```text
id
task_id
exposure_score
color_score
sharpness_score
noise_score
saturation_score
underwater_cast_score
overall_score
decision
reason_summary
detail_json
created_at
```

역할:

```text
PASS / REVIEW_REQUIRED / FAILED 결정 근거 저장
각 품질 항목 점수 저장
최종 overall_score 저장
간단한 사유 요약 저장
```

상세 품질 분석 파일은 artifact로 저장하고, DB에는 필요한 요약과 점수만 저장한다.

### feedback_records

사용자 피드백과 수동 수정 비교 데이터를 저장한다.

저장 데이터:

```text
id
task_id
user_action
rating
reason_tags
ai_settings_json
final_settings_json
manual_edit_delta_json
accepted
created_at
```

역할:

```text
사용자가 AI 결과를 수락했는지 기록
별점/평가 기록
거절 또는 수정 이유 기록
AI 적용 설정과 최종 사용자 수정 설정 비교
manual edit delta 저장
```

이 데이터는 로컬 feedback learning의 기초 데이터다.

### learning_samples

향후 planner calibration, style profile, camera profile, offline fine-tune 후보를 위한 로컬 학습 후보 메타데이터를 저장한다.

저장 데이터:

```text
id
task_id
feedback_id
sample_type
sample_status
dataset_path
metadata_json
created_at
updated_at
```

역할:

```text
planner calibration 후보 등록
user style profile 후보 등록
camera/lens/scene profile 후보 등록
future offline model fine-tune 후보 등록
```

주의:

```text
MVP는 normal photo processing 중 자동 fine-tuning을 수행하지 않는다.
learning_samples는 학습 실행 데이터가 아니라 후보/메타데이터 기록이다.
```

### v_task_summary

작업 목록 조회용 read-only view다.

포함 데이터:

```text
id
file_name
file_ext
status
current_stage
retry_count
overall_score
quality_decision
error_code
failed_stage
created_at
updated_at
completed_at
artifact_count
event_count
```

역할:

```text
CLI status/tasks 조회
운영자 확인
DBeaver에서 작업 상태 요약 확인
```

## 파일시스템에 저장되는 데이터

기본 artifact root:

```text
runtime/artifacts/
```

예상 artifact 파일:

```text
exif.json
preview.jpg
vision_prompt.txt
vision_raw_response.json
vision_structured.json
correction_plan.json
lightroom_request.json
lightroom_response.json
quality_detail.json
recovery_decision.json
retry_history.json
ai_settings.json
final_settings.json
manual_edit_delta.json
user_feedback.json
feedback_record.json
training_sample_manifest.json
```

PostgreSQL은 이 파일들의 본문이 아니라 다음 정보만 저장한다.

```text
task_id
artifact_type
artifact_path
size_bytes
sha256
mime_type
version
created_at
```

## 복구와 무결성

복구는 로그가 아니라 다음 근거로 수행한다.

```text
PostgreSQL image_tasks 상태
task_artifacts row
artifact 파일 존재 여부
artifact SHA-256 checksum
Lightroom response/export 파일 존재 여부
quality_results
task_events
stage_results
```

로그는 진단용이며 recovery source of truth가 아니다.

## 개인정보와 로컬 우선 정책

로컬에 유지해야 하는 데이터:

```text
원본 사진
preview
prompt
raw model response
Lightroom export
quality detail
feedback record
manual edit delta
training candidate
local path
GPS
device/customer identity
```

T-032 이후 허용되는 원격 전송은 privacy-scrubbed allowlisted structured analysis request를 승인된 Planner API로 보내는 경우뿐이다.

## 요약

PostgreSQL에 저장하는 것은 다음이다.

```text
작업 상태
stage 진행 상황
artifact 파일 인덱스
checksum
이벤트 이력
품질 점수와 결정
사용자 피드백
학습 후보 메타데이터
복구에 필요한 증거
```

PostgreSQL에 저장하지 않는 것은 다음이다.

```text
이미지 바이너리
대용량 model output
대용량 prompt/detail 파일
Lightroom export 바이너리
외부 전송용 개인정보 원문
```

즉 Tonevyra AI Agent의 PostgreSQL은 이미지 저장소가 아니라, 로컬-first 사진 처리 파이프라인을 안전하게 복구하고 추적하기 위한 운영 메타데이터 저장소다.
