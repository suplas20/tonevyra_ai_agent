# T-019 Folder-Driven Lightroom Plugin Automation Implementation

문서 목적: 이 문서는 Tonevyra AI 프로젝트에서 Lightroom Classic 플러그인을 실제 구현하고, 설치된 Lightroom Classic 환경에서 폴더 감지 기반 자동 보정을 검증하기 위한 작업 지시서이다.

적용 범위: 이 작업은 기존 fake Lightroom worker를 삭제하거나 대체하는 작업이 아니다. 기존 fake worker는 자동 하네스와 회귀 테스트를 위해 유지하고, 실제 Lightroom Classic을 자동 보정 작업자로 사용하는 real plugin / real bridge 경로를 추가한다.

중요 정정: Tonevyra AI의 기본 사용 흐름은 사용자가 Lightroom에서 사진을 선택하고 메뉴를 누르는 방식이 아니다. 사용자는 지정된 입력 폴더에 사진을 넣어 두고, Tonevyra agent가 이를 감지하여 분석하고, 최적 correction plan을 만든 뒤, Lightroom Classic 플러그인을 통해 자동으로 보정값을 적용한다.

---

## 1. 배경

Tonevyra AI의 현재 파이프라인은 하네스, 스킬, 루프 엔지니어링, 품질 게이트, DB evidence 기록 구조가 업데이트된 상태이다. 다음 단계는 지정 폴더에 들어온 사진을 agent가 감지하고, 로컬 모델 또는 deterministic MVP planner가 correction plan을 만든 뒤, Lightroom Classic 플러그인이 해당 보정값을 실제 Lightroom catalog/photo에 적용하는 실구현이다.

Tonevyra에서 Lightroom 플러그인은 AI 실행부가 아니다. Lightroom 플러그인은 Lightroom Classic 내부에서 실행되는 자동 적용 작업자이며, Python agent가 만든 apply request를 읽고 Lightroom Develop setting을 적용한 뒤 결과 evidence를 다시 남기는 얇은 bridge이다.

핵심 판단:

- 사용자는 보정할 사진을 Lightroom에서 직접 선택하지 않는다.
- 사용자는 지정 입력 폴더에 사진을 넣는다.
- Folder watcher / agent가 새 사진을 감지한다.
- Python agent가 분석, planning, quality gate, DB evidence 기록을 담당한다.
- Lightroom 플러그인은 agent가 만든 보정 적용 요청을 읽고 Lightroom에 적용한다.
- Lightroom 플러그인은 AI 모델을 직접 실행하지 않는다.
- Lightroom 플러그인은 PostgreSQL에 직접 접근하지 않는다.
- Lightroom 플러그인은 correction plan을 생성하지 않는다.
- Lightroom 플러그인은 원본 이미지 파일을 직접 수정하거나 덮어쓰지 않는다.

---

## 2. 제품 흐름

T-019의 목표는 다음 흐름을 실제로 작동시키는 것이다.

```text
사용자가 지정 입력 폴더에 사진 파일 추가
→ folder watcher가 파일 안정화 확인
→ Tonevyra agent가 task 생성
→ metadata / safe preview 생성
→ vision analysis 또는 MVP deterministic analysis 수행
→ correction plan / develop settings 생성
→ quality gate와 safety clamp 수행
→ agent가 Lightroom apply request JSON 작성
→ Lightroom plugin worker가 apply request 감지
→ Lightroom catalog에서 source_path에 해당하는 사진을 찾거나 필요 시 가져오기/import 처리
→ Lightroom plugin이 Develop parameter 적용
→ Lightroom plugin이 apply result / live evidence JSON 작성
→ agent가 task_events.payload_json / artifact evidence와 연결
→ task 완료 또는 recoverable failure 기록
```

이 작업이 끝나면 Tonevyra는 fake worker만 있는 상태가 아니라, 실제 Lightroom Classic을 자동 보정 작업자로 사용하는 실사용 경로를 갖게 된다.

---

## 3. 구현 원칙

### 3.1 기존 컨셉 유지

기존 설계의 핵심은 폴더 기반 자동 처리이다. T-019 구현은 이 컨셉을 절대 바꾸면 안 된다. Lightroom UI에서 사진을 선택하고 실행하는 방식은 기본 제품 흐름이 아니며, 디버그 또는 진단 메뉴로만 허용된다.

금지되는 기본 UX:

```text
Lightroom에서 사진 선택
→ 메뉴 클릭
→ 선택 사진 보정
```

허용되는 기본 UX:

```text
입력 폴더에 사진 추가
→ agent 자동 감지
→ agent 자동 분석
→ Lightroom plugin 자동 적용
→ evidence 자동 기록
```

### 3.2 기존 구조 유지

기존 프로젝트 구조, 스킬, 하네스, DB evidence 구조를 임의로 갈아엎지 않는다. 기존 fake worker, fake Lightroom test, smoke pipeline, quality gate, recovery harness는 계속 통과해야 한다.

### 3.3 플러그인은 얇게 유지

Lightroom Lua plugin은 다음 역할만 수행한다.

- agent가 작성한 apply request JSON 감지
- request schema 최소 검증
- source_path에 해당하는 Lightroom photo 찾기 또는 import/attach 처리
- 허용된 Develop parameter 적용
- 적용 성공/실패/부분 적용 evidence 작성
- 플러그인 상태/오류를 진단 메뉴 또는 로그로 표시

다음 역할은 금지한다.

- 입력 폴더 감지의 source of truth 역할
- AI 모델 로딩
- vision analysis 수행
- correction planning 수행
- quality score 계산
- PostgreSQL 직접 연결
- 인터넷 API 호출
- Lightroom catalog 파일 직접 조작
- 원본 파일 직접 수정
- 사용자가 선택한 사진을 기본 처리 대상으로 삼는 UX

### 3.4 원본 보존

T-019에서는 원본 파일을 직접 덮어쓰지 않는다. 적용은 Lightroom Develop setting, virtual copy, preset/application layer, 또는 catalog상의 비파괴 편집 경로를 통해 이루어져야 한다. 실패 시 원본 파일은 그대로 보존되어야 한다.

### 3.5 evidence 우선

T-019는 단순히 UI에서 보정이 되는지만 보는 작업이 아니다. 모든 주요 단계는 evidence로 남아야 한다.

필수 evidence:

- folder watcher task 생성 evidence
- agent correction plan evidence
- Lightroom apply request JSON
- Lightroom apply result JSON
- applied develop parameter summary
- skipped setting summary
- 실패한 경우 error code / error message / recoverable 여부
- task_events.payload_json 연결 정보

---

## 4. 구현 범위

### 4.1 파일/폴더 구조

다음 중 하나의 위치를 사용한다. 현재 프로젝트 구조에 이미 plugin 위치가 있으면 기존 위치를 우선한다.

```text
lightroom/TonevyraAI.lrplugin/
  Info.lua
  Init.lua
  Worker.lua
  Bridge.lua
  Json.lua 또는 JsonLight.lua
  README.md
```

또는 기존 프로젝트가 이미 다음 경로를 사용한다면 이 위치를 유지한다.

```text
src/tonevyra_agent/lightroom/plugin/TonevyraAI.lrplugin/
  Info.lua
  Init.lua
  Worker.lua
  Bridge.lua
  Json.lua 또는 JsonLight.lua
  README.md
```

둘 중 하나만 canonical path로 정하되, 하네스에서 감지 가능해야 한다.

### 4.2 Info.lua 요구사항

`Info.lua`는 최소한 다음 성격을 가져야 한다.

- `LrToolkitIdentifier`가 Tonevyra 고유 식별자를 사용한다.
- `LrPluginName`은 `Tonevyra AI` 또는 그에 준하는 명칭을 사용한다.
- 플러그인 초기화 시 background worker 또는 bridge loop를 시작할 수 있는 entrypoint를 제공한다.
- 메뉴 항목은 선택 사진 보정 실행용이 아니라 상태 확인, bridge 재시작, diagnostics, manual apply request replay 같은 보조 기능으로만 제공한다.

권장 예시:

```lua
return {
  LrSdkVersion = 6.0,
  LrToolkitIdentifier = "com.tonevyra.ai.agent",
  LrPluginName = "Tonevyra AI",
  LrInitPlugin = "Init.lua",
  LrShutdownPlugin = "Shutdown.lua",
  LrLibraryMenuItems = {
    {
      title = "Tonevyra Bridge Status",
      file = "Status.lua",
    },
  },
}
```

### 4.3 Worker.lua 요구사항

`Worker.lua` 또는 이에 준하는 파일은 다음 기능을 가져야 한다.

- `runtime/bridge/lightroom_apply_requests/`를 폴링하거나 Lightroom이 허용하는 방식으로 apply request를 감지한다.
- request JSON을 atomic read 방식으로 읽는다.
- request의 `schema_version`, `command`, `task_id`, `source_path`, `develop_settings`를 검증한다.
- `source_path`가 실제 파일인지 확인한다.
- Lightroom catalog에서 해당 `source_path`에 대응하는 photo를 찾는다.
- catalog에 없으면 T-019 MVP에서 가져오기/import를 지원하거나, 명확한 recoverable failure를 남긴다.
- 허용된 Develop parameter만 적용한다.
- 적용 불가능한 parameter는 `skipped_settings`에 남긴다.
- 성공, 실패, 부분 성공 결과를 `runtime/bridge/lightroom_apply_results/<request_id>.json`에 기록한다.
- 처리 완료된 apply request는 `processed/` 또는 `errors/`로 이동시키거나 idempotent marker를 남긴다.

### 4.4 Python agent 요구사항

Python agent 쪽에는 다음 처리가 있어야 한다.

- folder watcher가 지정 입력 폴더를 감지한다.
- 파일 안정화 후 task를 생성한다.
- source_path 기반 metadata / preview / vision analysis를 수행한다.
- correction plan을 생성한다.
- Lightroom에 적용 가능한 MVP subset으로 develop_settings를 clamp한다.
- apply request JSON을 `runtime/bridge/lightroom_apply_requests/<request_id>.json`에 작성한다.
- Lightroom plugin의 apply result를 기다리거나 후속 loop에서 수거한다.
- apply result를 DB와 `task_events.payload_json`에 연결한다.
- timeout 또는 실패는 recoverable state로 남긴다.

### 4.5 MVP correction parameter subset

초기 실구현에서는 모든 Lightroom 값을 지원하지 않는다. 다음 subset을 우선 지원한다.

| Tonevyra key | Lightroom develop meaning | 권장 범위 | 비고 |
|---|---:|---:|---|
| exposure | Exposure | -5.0 ~ +5.0 | MVP에서는 -1.5 ~ +1.5 권장 |
| contrast | Contrast | -100 ~ +100 | clamp 필수 |
| highlights | Highlights | -100 ~ +100 | clamp 필수 |
| shadows | Shadows | -100 ~ +100 | clamp 필수 |
| whites | Whites | -100 ~ +100 | clamp 필수 |
| blacks | Blacks | -100 ~ +100 | clamp 필수 |
| temp | Temperature | 구현 확인 필요 | 환경별 SDK 적용 가능성 확인 |
| tint | Tint | 구현 확인 필요 | 환경별 SDK 적용 가능성 확인 |
| vibrance | Vibrance | -100 ~ +100 | clamp 필수 |
| saturation | Saturation | -100 ~ +100 | clamp 필수 |
| texture | Texture | -100 ~ +100 | 적용 가능 여부 확인 |
| clarity | Clarity | -100 ~ +100 | clamp 필수 |
| dehaze | Dehaze | -100 ~ +100 | 적용 가능 여부 확인 |
| sharpening | Sharpening Amount | 0 ~ 150 | mapping 명시 |
| noise_reduction | Luminance Noise Reduction | 0 ~ 100 | mapping 명시 |

`temp`, `texture`, `dehaze` 등은 Lightroom SDK 버전과 실제 적용 API에 따라 차이가 있을 수 있으므로, T-019에서는 적용 가능 여부를 live test evidence에 기록한다.

---

## 5. Bridge JSON 계약

### 5.1 Agent → Lightroom apply request

파일 위치:

```text
runtime/bridge/lightroom_apply_requests/<request_id>.json
```

예시:

```json
{
  "schema_version": "t019.lightroom_apply.request.v1",
  "request_id": "lr-apply-20260617-000001",
  "request_origin": "tonevyra_agent",
  "command": "APPLY_LIGHTROOM_SETTINGS",
  "task_id": "task-20260617-000001",
  "source_path": "C:/Users/example/Tonevyra/input/test_image.dng",
  "correction_plan_id": "plan-20260617-000001",
  "created_at": "2026-06-17T15:30:00+09:00",
  "develop_settings": {
    "exposure": 0.35,
    "contrast": 12,
    "highlights": -18,
    "shadows": 22,
    "whites": 8,
    "blacks": -10,
    "vibrance": 10,
    "clarity": 5
  },
  "safety": {
    "clamped": true,
    "source_hash": "optional-sha256",
    "non_destructive_required": true
  },
  "runtime_context": {
    "input_folder": "C:/Users/example/Tonevyra/input",
    "runtime_dir": "C:/Users/example/Tonevyra/runtime"
  }
}
```

필수 필드:

- `schema_version`: `t019.lightroom_apply.request.v1`
- `request_id`: 고유 문자열
- `request_origin`: `tonevyra_agent`
- `command`: `APPLY_LIGHTROOM_SETTINGS`
- `task_id`
- `source_path`: absolute path
- `created_at`: ISO8601 문자열
- `develop_settings`: 허용된 correction subset
- `safety.non_destructive_required`: true

### 5.2 Lightroom → Agent apply result

파일 위치:

```text
runtime/bridge/lightroom_apply_results/<request_id>.json
```

성공 예시:

```json
{
  "schema_version": "t019.lightroom_apply.result.v1",
  "request_id": "lr-apply-20260617-000001",
  "request_origin": "lightroom_plugin",
  "command": "APPLY_LIGHTROOM_SETTINGS",
  "task_id": "task-20260617-000001",
  "status": "applied",
  "source_path": "C:/Users/example/Tonevyra/input/test_image.dng",
  "applied_settings": {
    "exposure": 0.35,
    "contrast": 12,
    "highlights": -18,
    "shadows": 22
  },
  "skipped_settings": {},
  "lightroom_result": {
    "plugin_loaded": true,
    "worker_running": true,
    "source_photo_found": true,
    "source_photo_imported": false,
    "develop_settings_applied": true
  },
  "evidence": {
    "lightroom_catalog_photo_id": "optional",
    "applied_at": "2026-06-17T15:31:10+09:00"
  }
}
```

실패 예시:

```json
{
  "schema_version": "t019.lightroom_apply.result.v1",
  "request_id": "lr-apply-20260617-000002",
  "request_origin": "lightroom_plugin",
  "command": "APPLY_LIGHTROOM_SETTINGS",
  "task_id": "task-20260617-000002",
  "status": "failed",
  "source_path": "C:/Users/example/Tonevyra/input/missing.dng",
  "applied_settings": {},
  "skipped_settings": {},
  "error": {
    "code": "SOURCE_PATH_NOT_FOUND",
    "message": "The source path from folder watcher does not exist.",
    "recoverable": true
  },
  "lightroom_result": {
    "plugin_loaded": true,
    "worker_running": true,
    "source_photo_found": false,
    "source_photo_imported": false,
    "develop_settings_applied": false
  }
}
```

---

## 6. 하네스 요구사항

T-019 하네스는 기존 선택 사진 기반 설계가 다시 들어오지 못하게 막아야 한다.

필수 검증:

1. 플러그인 구조 검증
   - `Info.lua` 존재
   - Tonevyra identity 존재
   - background worker/init entrypoint 존재
   - Lua plugin 내부에 AI 모델, DB, network, 원본 삭제 코드가 없는지 확인
   - Lightroom UI의 현재 선택 항목을 기본 처리 흐름으로 암시하는 토큰이 없는지 확인

2. Bridge contract 검증
   - apply request schema 검증
   - apply result schema 검증
   - `request_origin = tonevyra_agent` / `lightroom_plugin` 방향성 검증
   - `command = APPLY_LIGHTROOM_SETTINGS` 검증
   - `source_path`, `task_id`, `develop_settings` 필수성 검증

3. Worker mapping 검증
   - MVP Develop parameter subset만 허용
   - 범위 초과 값 clamp 또는 거부
   - unsupported key는 `skipped_settings`로 기록

4. Live evidence 검증
   - `worker_running = true`
   - `source_photo_found` 또는 `source_photo_imported` 중 하나가 true
   - `develop_settings_applied = true`일 때 applied_settings가 비어 있지 않아야 함
   - 실패 시 error code/message/recoverable 필수

5. Folder-driven invariant 검증
   - 작업 지시서, 스킬, 하네스, fixture에 사용자 선택 사진 기반 흐름이 기본 UX로 들어오지 않아야 함
   - 수동 테스트는 사진 선택이 아니라 입력 폴더에 파일 추가로 시작해야 함

---

## 7. 실제 Lightroom 테스트 절차

### 7.1 사전 조건

- Lightroom Classic 설치 완료
- Tonevyra agent 실행 가능
- `TONEVYRA_INPUT_DIR` 또는 프로젝트 입력 폴더 설정 완료
- `TONEVYRA_RUNTIME_DIR` 설정 완료
- 테스트용 사진 1장 준비
- 기존 하네스 통과 상태 확인

### 7.2 설치/로드 테스트

1. Lightroom Classic 실행
2. Plug-in Manager에서 `TonevyraAI.lrplugin` 추가
3. 플러그인 상태 확인
   - 기대값: Installed and running
4. Tonevyra bridge worker 상태 확인
   - 기대값: worker running 또는 diagnostics에서 정상 표시

### 7.3 자동 보정 live test

1. Lightroom에서 사진을 선택하지 않는다.
2. 테스트 사진 1장을 지정 입력 폴더에 복사한다.
3. agent folder watcher가 task를 생성하는지 확인한다.
4. agent가 correction plan을 생성하는지 확인한다.
5. apply request JSON 생성 확인
   - 위치: `runtime/bridge/lightroom_apply_requests/<request_id>.json`
6. Lightroom plugin worker가 request를 처리하는지 확인한다.
7. apply result JSON 생성 확인
   - 위치: `runtime/bridge/lightroom_apply_results/<request_id>.json`
8. Lightroom에서 해당 사진에 보정값이 적용되었는지 확인한다.
9. DB의 `task_events.payload_json` 또는 artifact evidence에 연결되었는지 확인한다.

### 7.4 실패 테스트

다음 실패 시나리오 중 가능한 항목을 최소 2개 검증한다.

- Lightroom plugin이 실행되지 않은 상태에서 apply request 생성
- source path missing
- invalid apply request schema
- unsupported develop parameter 포함
- response/apply result timeout
- catalog import 실패

각 실패는 사용자 선택 사진 오류가 아니라 자동 처리 실패 evidence로 남아야 한다.

---

## 8. 완료 기준

T-019는 다음 조건을 만족해야 완료로 본다.

1. 지정 폴더에 사진을 넣으면 agent가 task를 생성한다.
2. agent가 correction plan과 Lightroom apply request를 만든다.
3. Lightroom plugin이 apply request를 감지한다.
4. plugin이 source_path 기반으로 Lightroom photo를 찾거나 가져오기/import 처리한다.
5. plugin이 최소 1개 이상의 Develop setting을 적용한다.
6. apply result JSON이 생성된다.
7. task_events.payload_json 또는 artifact evidence에 적용 결과가 연결된다.
8. 기존 fake worker와 기존 하네스는 계속 통과한다.
9. T-019 전용 하네스가 모두 통과한다.
10. 문서/스킬/하네스 어디에도 기본 흐름을 선택 사진 기반으로 되돌리는 내용이 없어야 한다.

---

## 9. Codex 작업 원칙

Codex는 이 작업을 수행할 때 다음 원칙을 따라야 한다.

- 기존 설계를 뒤집지 말 것.
- 사용자 입력은 Lightroom 선택이 아니라 폴더 투입이다.
- Lightroom plugin은 agent가 만든 apply request의 실행자이다.
- 폴더 감지, 분석, 보정 계획, 품질 판단, DB 기록은 Python agent가 담당한다.
- Lua plugin은 Lightroom 내부 적용만 담당한다.
- 실구현 중 실제 Lightroom SDK 제약이 발견되면 UX를 바꾸지 말고, recoverable limitation으로 기록한 뒤 우회 설계를 제안한다.
- 사용자가 매번 사진을 선택해야 하는 구조로 회귀하지 말 것.
