# T-020 — Lightroom Final Export Adapter 구현 작업서

## 1. 문서 상태

```text
Ticket: T-020
Title: Lightroom Final Export Adapter
Project root: F:\tonevyra_ai_agent
Precondition: T-019 Lightroom Apply Adapter 완료
Primary goal: Lightroom에 적용된 보정 결과를 사용자 조작 없이 최종 이미지 파일로 내보내기
```

이 문서는 T-020 구현의 최우선 작업 기준이다. `AGENTS.md`가 최상위 규칙이며, 본 문서는 T-020 범위와 완료 조건을 구체화한다. 스킬과 하네스는 본 문서의 구현을 보조하고 검증하는 수단이다.

---

## 2. 배경

T-019에서 다음 흐름이 실제 Lightroom Classic 환경에서 성공했다.

```text
Agent가 apply request 생성
→ Lightroom Plugin이 request 자동 처리
→ source_path 사진을 catalog에서 find/import
→ Develop settings 적용
→ apply result JSON 생성
→ status = applied
```

T-019 성공으로 Lightroom 카탈로그에는 비파괴 보정값이 적용되지만, 사용자가 사용할 수 있는 최종 JPG/TIFF 파일은 아직 자동 생성되지 않는다. 현재는 사용자가 Lightroom Classic에서 수동으로 내보내야 한다.

T-020은 이 수동 내보내기 단계를 자동화한다.

---

## 3. T-020의 한 문장 목표

> T-019에서 보정 적용이 성공한 사진을 Lightroom Classic Plugin이 자동으로 내보내고, 실제 출력 파일과 export result JSON을 생성한다.

---

## 4. 제품 흐름

```text
Input image
→ Agent task
→ Vision/Mock analysis
→ Correction Planner
→ T-019 apply request
→ Lightroom Plugin applies Develop settings
→ T-019 apply result: status=applied
→ Agent creates T-020 export request
→ Lightroom Plugin exports corrected rendition
→ output file is created
→ T-020 export result: status=exported
→ Agent verifies output
→ EXPORT_DONE
→ Quality Gate
```

T-020은 T-019를 대체하지 않는다. T-019의 성공 결과를 전제 조건으로 사용하는 다음 단계다.

---

## 5. 역할 분리

### 5.1 Python Agent의 책임

Agent는 다음을 담당한다.

1. T-019 apply result를 수집한다.
2. apply result가 실제 성공인지 검증한다.
3. `status=applied`이고 `develop_settings_applied=true`인 작업만 export 대상으로 만든다.
4. 절대 경로 기반 export request JSON을 생성한다.
5. export request와 result를 task/artifact/event 증거로 기록한다.
6. export result를 수집하고 실제 출력 파일을 검증한다.
7. 성공 시 task를 `EXPORT_DONE`으로 전이한다.
8. 실패 시 기존 error code 정책에 따라 구조화된 실패를 기록한다.
9. result가 늦는 경우 무한 대기하지 않고 bounded timeout/recovery 정책을 사용한다.

### 5.2 Lightroom Plugin의 책임

Plugin은 다음을 담당한다.

1. `lightroom_export_requests`의 Agent 생성 요청을 자동 확인한다.
2. export request schema와 필수 필드를 검증한다.
3. `source_path`에 해당하는 Lightroom catalog photo를 찾는다.
4. T-019에서 적용된 현재 Develop 상태를 사용한다.
5. request에 지정된 export 설정으로 Lightroom SDK export를 수행한다.
6. export 완료 여부와 실제 출력 파일 생성을 확인한다.
7. 성공 또는 실패 export result JSON을 반드시 기록한다.
8. 요청을 결과 없이 삭제하거나 유실하지 않는다.

### 5.3 Plugin이 하면 안 되는 일

Plugin은 다음을 하면 안 된다.

- `runtime\input` 또는 사용자 이미지 폴더 감시
- 사진 분석 또는 모델 추론
- Correction Plan 생성 또는 수정
- 보정값 재계산
- Quality Gate 점수 계산 또는 PASS/REVIEW/FAILED 결정
- PostgreSQL 직접 접근
- Agent 전체 파이프라인 오케스트레이션
- selected photo 기반의 수동 내보내기를 정식 제품 경로로 사용
- 사용자가 Lightroom 메뉴를 눌러야만 동작하는 manual-only 구조
- 원본 파일 덮어쓰기
- UI 클릭 자동화

진단용 메뉴는 허용되지만 기존 bridge export request를 수동으로 한 번 처리하는 디버그 기능이어야 하며 정식 제품 흐름을 대체하면 안 된다.

---

## 6. 정식 Bridge 경로

```text
Project root:
F:\tonevyra_ai_agent

Plugin:
F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin

Export request directory:
F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_requests

Export result directory:
F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_results

Temporary corrected output root:
F:\tonevyra_ai_agent\runtime\output\temp
```

모든 request의 `source_path`와 `export_path`는 정규화된 절대 경로여야 한다. 프로세스의 current working directory에 의존하면 안 된다.

T-020 단계에서는 출력물을 `runtime\output\temp`에 생성한다. 이후 Quality Gate가 결과에 따라 `pass`, `review_required`, `failed` 영역으로 분류·이동하는 기존 제품 흐름을 유지한다.

---

## 7. Export 전제 조건

Agent는 다음 조건을 모두 충족할 때만 export request를 생성한다.

```text
apply_result.status == "applied"
lightroom_result.develop_settings_applied == true
catalog_action in {"imported", "found_existing"}
source_photo_imported == true OR source_photo_found == true
```

필드 구조가 버전에 따라 달라질 수 있으므로, 구현은 schema version에 맞춰 검증해야 한다. 단순히 Agent 로그에 `LIGHTROOM_REQUESTED`가 있다는 이유만으로 export를 시작하면 안 된다.

---

## 8. Export Request 계약

### 8.1 필수 필드

```text
schema_version
request_id
task_id
apply_request_id
source_path
export_path
command
export_settings
created_at
```

### 8.2 권장 request 예시

```json
{
  "schema_version": "t020.lightroom_export.request.v1",
  "request_id": "export-7f57c5f0-5a0e-4f20-a7e1-0d7b84a1e101",
  "task_id": "f1e1a046-85b7-4b98-8ea7-4aabeea59c46",
  "apply_request_id": "f1e1a046-85b7-4b98-8ea7-4aabeea59c46",
  "source_path": "F:\\tonevyra_ai_agent\\runtime\\input\\test.jpg",
  "export_path": "F:\\tonevyra_ai_agent\\runtime\\output\\temp\\f1e1a046-85b7-4b98-8ea7-4aabeea59c46\\test_tonevyra.jpg",
  "command": "EXPORT_CORRECTED_IMAGE",
  "export_settings": {
    "format": "JPEG",
    "quality": 95,
    "color_space": "sRGB",
    "resize": false,
    "output_sharpening": {
      "enabled": true,
      "medium": "screen",
      "amount": "standard"
    },
    "metadata_policy": "copyright_and_capture_only",
    "overwrite": false
  },
  "created_at": "2026-06-19T12:00:00Z"
}
```

### 8.3 MVP 기본 설정

```text
Format: JPEG
Quality: 95
Color space: sRGB
Resize: false
Resolution: original dimensions
Output sharpening: screen / standard
Overwrite original: forbidden
Overwrite existing output: false
```

MVP에서는 JPEG export를 우선 구현한다. TIFF, PNG, DNG, 여러 export preset 동시 처리, 클라우드 업로드는 T-020 범위가 아니다.

---

## 9. Export Result 계약

### 9.1 필수 필드

```text
schema_version
request_id
task_id
apply_request_id
source_path
export_path
status
export_settings
lightroom_result
file_result
error_code
message
completed_at
```

### 9.2 성공 result 예시

```json
{
  "schema_version": "t020.lightroom_export.result.v1",
  "request_id": "export-7f57c5f0-5a0e-4f20-a7e1-0d7b84a1e101",
  "task_id": "f1e1a046-85b7-4b98-8ea7-4aabeea59c46",
  "apply_request_id": "f1e1a046-85b7-4b98-8ea7-4aabeea59c46",
  "source_path": "F:\\tonevyra_ai_agent\\runtime\\input\\test.jpg",
  "export_path": "F:\\tonevyra_ai_agent\\runtime\\output\\temp\\f1e1a046-85b7-4b98-8ea7-4aabeea59c46\\test_tonevyra.jpg",
  "status": "exported",
  "export_settings": {
    "format": "JPEG",
    "quality": 95,
    "color_space": "sRGB",
    "resize": false
  },
  "lightroom_result": {
    "plugin_loaded": true,
    "worker_running": true,
    "source_photo_found": true,
    "export_started": true,
    "export_completed": true,
    "plugin_version": "t020-lightroom-final-export-adapter"
  },
  "file_result": {
    "exists": true,
    "size_bytes": 8245321,
    "width": 6000,
    "height": 4000
  },
  "error_code": null,
  "message": "Export completed successfully",
  "completed_at": "2026-06-19T12:00:18Z"
}
```

### 9.3 실패 result 예시

```json
{
  "schema_version": "t020.lightroom_export.result.v1",
  "request_id": "export-7f57c5f0-5a0e-4f20-a7e1-0d7b84a1e101",
  "task_id": "f1e1a046-85b7-4b98-8ea7-4aabeea59c46",
  "apply_request_id": "f1e1a046-85b7-4b98-8ea7-4aabeea59c46",
  "source_path": "F:\\tonevyra_ai_agent\\runtime\\input\\test.jpg",
  "export_path": "F:\\tonevyra_ai_agent\\runtime\\output\\temp\\f1e1a046-85b7-4b98-8ea7-4aabeea59c46\\test_tonevyra.jpg",
  "status": "failed",
  "export_settings": {
    "format": "JPEG",
    "quality": 95,
    "color_space": "sRGB",
    "resize": false
  },
  "lightroom_result": {
    "plugin_loaded": true,
    "worker_running": true,
    "source_photo_found": true,
    "export_started": true,
    "export_completed": false
  },
  "file_result": {
    "exists": false,
    "size_bytes": 0
  },
  "error_code": "LIGHTROOM_EXPORT_FAILED",
  "recoverable": true,
  "message": "Lightroom export did not complete within the bounded timeout",
  "completed_at": "2026-06-19T12:05:18Z"
}
```

---

## 10. 성공 판정 규칙

T-020은 JSON의 `status=exported`만으로 성공 처리하면 안 된다. 다음 조건을 모두 검증해야 한다.

```text
result.status == "exported"
lightroom_result.export_completed == true
file_result.exists == true
file_result.size_bytes > 0
export_path 파일이 실제로 존재
export_path가 source_path와 다름
export_path가 요청된 output root 내부
```

가능하면 Agent가 파일 크기, MIME/확장자, 해상도와 SHA-256을 계산하고 Artifact Storage에 등록한다.

---

## 11. 상태 전이

기존 `AGENTS.md` 상태를 유지하고 새 상태 문자열을 추가하지 않는다.

권장 전이:

```text
LIGHTROOM_REQUESTED
→ LIGHTROOM_PROCESSING
→ T-019 apply success
→ T-020 export request created
→ export processing remains LIGHTROOM_PROCESSING
→ export success + file verification
→ EXPORT_DONE
→ QUALITY_CHECK
```

실패 시:

```text
LIGHTROOM_PROCESSING
→ bounded retry/recovery
→ FAILED when no safe retry remains
```

`EXPORT_DONE`은 result JSON만 존재하는 상태가 아니라 실제 export 파일이 검증되고 artifact로 등록된 상태여야 한다.

---

## 12. 오류 코드 정책

T-020은 우선 기존 `AGENTS.md`에 정의된 error code를 사용한다.

```text
LIGHTROOM_REQUEST_FAILED
LIGHTROOM_RESPONSE_TIMEOUT
LIGHTROOM_EXPORT_FAILED
EXPORT_FILE_MISSING
ARTIFACT_WRITE_FAILED
DB_WRITE_FAILED
```

새로운 세부 error code가 필요하다면 문서만 임의로 추가하면 안 된다. 다음을 함께 변경해야 한다.

```text
AGENTS.md
core enum/error definitions
DB CHECK constraints
Alembic migration
harness fixtures/tests
recovery logic
```

---

## 13. Timeout, Retry, Recovery

1. export 대기는 무한 대기하면 안 된다.
2. 기본 timeout은 설정 가능해야 하며 초기값은 300초를 권장한다.
3. timeout 발생 시 request를 삭제하지 않는다.
4. Agent는 durable request/result/output evidence를 확인해 안전한 단계에서 복구한다.
5. 같은 `request_id`의 중복 실행은 출력 파일을 무조건 덮어쓰지 않는다.
6. 이전 성공 result와 유효한 파일이 있으면 idempotent success로 회수할 수 있다.
7. result가 없고 request가 남아 있으면 bounded retry 대상으로 남긴다.
8. retry limit 초과 후에는 구조화된 실패와 recovery evidence를 기록한다.
9. 로그는 복구의 source of truth가 아니다.

---

## 14. 파일 안전 규칙

- 원본 `source_path`를 절대 수정하거나 덮어쓰지 않는다.
- export 경로는 task별 고유 디렉터리를 사용한다.
- export 파일을 최종적으로 검증하기 전 `EXPORT_DONE`으로 기록하지 않는다.
- Agent artifact 등록은 atomic write/checksum 정책을 따른다.
- 예상 경로 밖으로 export하는 path traversal을 거부한다.
- 빈 파일, 임시 파일, 부분 파일을 성공으로 인정하지 않는다.
- 동일한 request 재처리 시 파일 충돌 정책을 명확히 적용한다.

---

## 15. T-020에서 구현하지 않는 것

```text
- Vision AI 모델 연결 또는 변경
- Correction Planner 변경
- T-019 보정값 적용 로직 재작성
- Quality score 알고리즘 변경
- Lightroom 자동 실행·최소화·종료
- 여러 장 병렬 export
- 사용자 UI/dashboard
- Agent와 Plugin 저장소 분리
- TIFF/PNG/DNG 전체 포맷 지원
- 클라우드 업로드
- Lightroom 결과 기반 모델 학습
```

Worker concurrency는 MVP 정책대로 1을 유지한다.

---

## 16. 구현 순서

### Phase 1 — 계약과 fixture

1. export request/result schema 확정
2. valid/failed/invalid fixture 작성
3. export 전제 조건 정의
4. error/timeout/recovery 규칙 확정

### Phase 2 — Agent bridge

1. T-019 apply result 검증
2. export request writer 구현
3. absolute export path 생성
4. request artifact 및 DB evidence 등록
5. export result reader 구현
6. 실제 파일 검증 및 artifact 등록
7. `EXPORT_DONE` 상태 전이

### Phase 3 — Lightroom Plugin

1. export request directory 자동 확인
2. request claim/processing 처리
3. source photo 찾기
4. Lightroom export session 실행
5. rendition 완료/실패 수집
6. output 파일 존재 확인
7. export result 원자적 기록
8. request archive 또는 안전한 완료 처리

### Phase 4 — Recovery

1. request는 있으나 result가 없는 상태
2. result는 있으나 export 파일이 없는 상태
3. export 파일은 있으나 DB/artifact 등록이 없는 상태
4. Agent 재시작 후 `EXPORT_DONE` 복구
5. 중복 request idempotency 확인

### Phase 5 — 검증

1. static harness
2. fixture validation
3. fake Lightroom export test
4. 실제 Lightroom 단일 사진 export
5. 기존 T-019 apply 회귀 테스트
6. worker/smoke/recovery harness 실행

---

## 17. 하네스 명령

정적 계약 및 fixture 검증:

```powershell
cd F:\tonevyra_ai_agent
python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent
```

Plugin 코드까지 검사:

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py `
  --project-root F:\tonevyra_ai_agent `
  --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin `
  --strict
```

실제 export result와 출력 파일 검증:

```powershell
python .\harness\scripts\verify_lightroom_export_adapter.py `
  --project-root F:\tonevyra_ai_agent `
  --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin `
  --result-json F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_results\<result>.json `
  --require-output-file `
  --strict
```

기존 T-019 하네스와 일반 하네스도 회귀 실행한다.

---

## 18. T-020 완료 조건

T-020은 다음 조건을 모두 충족해야 완료다.

1. T-019 apply 성공 작업만 export request를 생성한다.
2. Agent가 유효한 export request JSON을 자동 생성한다.
3. Plugin이 수동 메뉴 조작 없이 request를 자동 처리한다.
4. Plugin이 `source_path`의 보정된 catalog photo를 찾는다.
5. Plugin이 요청된 설정으로 JPEG export를 수행한다.
6. `export_path`에 실제 파일이 생성된다.
7. 파일 크기가 0보다 크고 요청 경로와 형식이 일치한다.
8. 원본 사진은 변경되지 않는다.
9. export result JSON이 반드시 생성된다.
10. 성공 result는 `status=exported`를 사용한다.
11. Agent가 결과와 실제 파일을 확인한 뒤 `EXPORT_DONE`으로 전이한다.
12. request/result/output이 Artifact Storage와 DB evidence에 연결된다.
13. 재시작 시 미완료 export를 안전하게 복구할 수 있다.
14. T-019 apply adapter 회귀 테스트가 계속 통과한다.
15. 기존 harness/skills/documents의 내용과 기능이 훼손되지 않는다.

---

## 19. 완료 보고서 요구사항

구현 담당자는 완료 후 다음을 보고한다.

1. 변경 파일 목록
2. export request/result schema
3. 실제 생성된 output 경로
4. Lightroom export 설정
5. 실제 result JSON
6. 파일 크기와 해상도 검증 결과
7. T-019 회귀 테스트 결과
8. T-020 하네스 결과
9. fake/real Lightroom 테스트 구분
10. 남은 이슈와 후속 작업

---

## 20. 최종 판정 문장

> T-020은 `status=exported`인 result JSON과 실제로 존재하는 정상 출력 이미지 파일이 모두 확인될 때만 성공이다.
