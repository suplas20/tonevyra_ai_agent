# Codex Prompt - T-019 Folder-Driven Lightroom Plugin Automation

현재 프로젝트는 하네스와 스킬이 모두 통과한 상태다. 이제 `T-019 Folder-Driven Lightroom Plugin Automation Implementation`을 수행한다.

## 반드시 지켜야 할 핵심 컨셉

Tonevyra AI의 기본 UX는 사용자가 Lightroom에서 사진을 선택하고 메뉴를 누르는 방식이 아니다.

사용자는 지정된 입력 폴더에 사진을 넣는다. Tonevyra agent가 이를 감지하고, 사진을 분석하고, 최적 correction plan을 만든 뒤, Lightroom Classic 플러그인을 자동 적용 작업자로 사용해 보정값을 적용한다.

따라서 T-019 구현은 다음 흐름을 따라야 한다.

```text
input folder에 사진 추가
→ folder watcher task 생성
→ agent 분석/planning/quality gate
→ agent가 Lightroom apply request JSON 작성
→ Lightroom plugin worker가 apply request 감지
→ source_path 기반으로 Lightroom photo 찾기/import
→ Develop settings 적용
→ apply result/evidence JSON 작성
→ agent가 DB/task_events.payload_json에 연결
```

## 금지되는 회귀

다음 흐름을 기본 제품 흐름으로 구현하지 말 것.

```text
Lightroom에서 사진 선택
→ 사용자가 메뉴 클릭
→ 선택 사진 보정
```

메뉴는 bridge status, diagnostics, worker restart, manual replay 같은 보조 기능에만 사용할 수 있다. 사진 단위 보정 시작점은 folder watcher여야 한다.

## 구현 범위

1. 기존 fake Lightroom worker는 삭제하지 말고 regression/fallback 용도로 유지한다.
2. `lightroom/TonevyraAI.lrplugin/` 또는 기존 canonical plugin path에 Lightroom plugin을 구현한다.
3. `Info.lua`, `Init.lua`, `Worker.lua`, `Bridge.lua`, `Json.lua` 또는 동등 파일을 작성한다.
4. plugin은 background worker 또는 bridge loop로 `runtime/bridge/lightroom_apply_requests/`를 감시한다.
5. Python agent는 folder watcher task 처리 후 `APPLY_LIGHTROOM_SETTINGS` apply request를 작성한다.
6. plugin은 apply request를 읽고 `source_path` 기준으로 Lightroom photo를 찾거나 import한다.
7. plugin은 `develop_settings`의 허용된 MVP subset만 Lightroom에 적용한다.
8. plugin은 `runtime/bridge/lightroom_apply_results/<request_id>.json`에 결과를 쓴다.
9. agent는 apply result를 DB evidence와 `task_events.payload_json`에 연결한다.
10. 실패는 recoverable error로 남기고 조용히 무시하지 않는다.

## MVP Develop Parameter subset

- exposure
- contrast
- highlights
- shadows
- whites
- blacks
- temp
- tint
- vibrance
- saturation
- texture
- clarity
- dehaze
- sharpening
- noise_reduction

적용 불가능한 key는 `skipped_settings`에 남긴다.

## Bridge contract

Agent → Lightroom plugin:

```text
runtime/bridge/lightroom_apply_requests/<request_id>.json
schema_version = t019.lightroom_apply.request.v1
request_origin = tonevyra_agent
command = APPLY_LIGHTROOM_SETTINGS
```

Lightroom plugin → Agent:

```text
runtime/bridge/lightroom_apply_results/<request_id>.json
schema_version = t019.lightroom_apply.result.v1
request_origin = lightroom_plugin
command = APPLY_LIGHTROOM_SETTINGS
```

## 하네스 업데이트

다음 하네스를 추가/수정하라.

1. plugin structure harness
   - background worker/init entrypoint 확인
   - 선택 사진 기반 기본 흐름 토큰 금지
   - AI/DB/network/original deletion 금지

2. bridge contract harness
   - apply request/result schema 검증
   - 방향성 검증: agent -> plugin -> agent

3. worker mapping harness
   - allowed develop parameter subset
   - clamp/skipped_settings 검증

4. live evidence harness
   - folder-driven evidence 검증
   - selected_photo 기반 evidence 금지

## 실제 Lightroom 테스트

수동 live test도 사진 선택이 아니라 다음 방식으로 진행한다.

1. Lightroom Classic 실행
2. TonevyraAI.lrplugin 로드 확인
3. agent 실행
4. 테스트 사진을 지정 입력 폴더에 복사
5. task 생성 확인
6. apply request 생성 확인
7. Lightroom plugin 처리 확인
8. apply result 생성 확인
9. Lightroom에서 해당 사진의 보정값 적용 확인
10. task_events.payload_json 또는 artifact evidence 연결 확인

## 완료 기준

- 사용자가 Lightroom에서 사진을 선택하지 않아도 자동 보정 경로가 작동해야 한다.
- folder watcher가 처리 시작점이어야 한다.
- Lightroom plugin은 apply worker로만 동작해야 한다.
- 기존 fake worker와 기존 하네스가 계속 통과해야 한다.
- T-019 전용 하네스가 모두 통과해야 한다.
- 문서/스킬/하네스/fixture에서 기본 흐름이 선택 사진 기반으로 표현되지 않아야 한다.
