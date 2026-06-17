# T-019 Folder-Driven Lightroom Bridge Contract

이 계약은 Tonevyra Python agent와 Lightroom Classic plugin 사이의 파일 기반 bridge를 정의한다.

## 1. Direction

기본 방향은 다음과 같다.

```text
folder watcher / Python agent
→ Lightroom apply request
→ Lightroom plugin worker
→ Lightroom apply result
→ Python agent DB/evidence collector
```

Lightroom plugin이 사진 선택을 시작점으로 request를 만드는 구조가 아니다.

## 2. Directory contract

기본 runtime root는 `TONEVYRA_RUNTIME_DIR`을 우선 사용한다. 없으면 프로젝트의 기존 runtime 설정을 따른다.

```text
runtime/bridge/lightroom_apply_requests/
runtime/bridge/lightroom_apply_processing/
runtime/bridge/lightroom_apply_results/
runtime/bridge/lightroom_apply_errors/
runtime/bridge/lightroom_live_evidence/
```

## 3. Agent to Lightroom apply request

Agent가 Lightroom plugin에 적용 요청을 보낼 때는 `runtime/bridge/lightroom_apply_requests/<request_id>.json`에 JSON을 작성한다.

필수 필드:

- `schema_version`: `t019.lightroom_apply.request.v1`
- `request_id`: 고유 문자열
- `request_origin`: `tonevyra_agent`
- `command`: `APPLY_LIGHTROOM_SETTINGS`
- `task_id`
- `source_path`: absolute path
- `created_at`: ISO8601 문자열
- `develop_settings`
- `safety.non_destructive_required`: true

선택 필드:

- `correction_plan_id`
- `runtime_context.input_folder`
- `runtime_context.runtime_dir`
- `safety.source_hash`

## 4. Lightroom to Agent apply result

Lightroom plugin은 `runtime/bridge/lightroom_apply_results/<request_id>.json`에 result를 작성한다.

성공 또는 부분 성공 result 필수 필드:

- `schema_version`: `t019.lightroom_apply.result.v1`
- `request_id`
- `request_origin`: `lightroom_plugin`
- `command`: `APPLY_LIGHTROOM_SETTINGS`
- `task_id`
- `status`: `applied` 또는 `partial`
- `source_path`
- `applied_settings`
- `skipped_settings`
- `lightroom_result.plugin_loaded`
- `lightroom_result.worker_running`
- `lightroom_result.develop_settings_applied`

실패 result 필수 필드:

- `schema_version`
- `request_id`
- `request_origin`: `lightroom_plugin`
- `command`
- `task_id`
- `status`: `failed`
- `source_path`
- `error.code`
- `error.message`
- `error.recoverable`
- `lightroom_result.worker_running`

## 5. Develop settings contract

지원 key:

```text
exposure, contrast, highlights, shadows, whites, blacks,
temp, tint, vibrance, saturation, texture, clarity, dehaze,
sharpening, noise_reduction
```

모든 값은 Python agent에서 clamp되어야 한다. Lua plugin은 추가 방어로 범위를 재확인할 수 있지만, correction planning을 직접 수행해서는 안 된다.

## 6. Folder-driven invariant

T-019 계약은 Lightroom UI의 현재 선택 항목을 작업 시작점으로 삼지 않는다.

금지되는 패턴:

- plugin이 자체적으로 사진 선택 상태를 request source로 만드는 방식
- 메뉴 액션이 사진 단위 보정 작업을 직접 시작하는 방식
- catalog 내부 식별자를 folder watcher의 `source_path`보다 우선하는 방식

catalog 내부 식별자가 필요하면 `lightroom_catalog_photo_id`라는 evidence 필드로만 기록한다.
