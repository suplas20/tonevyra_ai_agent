# Tonevyra AI Agent — Harness

이 `harness/` 폴더는 Tonevyra AI Agent MVP가 **스킬과 계약을 실제로 지키며 구현되었는지 검증하는 실행 하네스**입니다.  
Mock Vision과 Fake Lightroom은 하네스의 전부가 아니라, 실제 Qwen 모델과 실제 Lightroom Classic을 연결하기 전에 규칙 위반을 빠르게 잡기 위한 통제된 검증 수단입니다.

## 하네스의 역할

```text
스킬/계약을 읽는다 → 구현한다 → 하네스가 증거를 검사한다 → 통과해야 완료 처리한다
```

하네스는 다음을 확인합니다.

- 에이전트가 스킬의 금지/필수 규칙을 우회하지 않았는지
- PostgreSQL 상태, task_events, stage_results, artifact가 일관적인지
- Mock/Fake 환경에서 end-to-end 파이프라인이 재현 가능하게 통과하는지
- 자동 루프가 무한 반복 없이 종료되고, loop evidence를 남기는지
- 보안 규칙상 런타임 네트워크, 원격 모델 다운로드, 외부 API 호출이 없는지
- 실패/중단 후 로그가 아니라 DB + artifact 근거로 복구 가능한지

## 핵심 원칙

```text
Mock Vision 통과 전 실제 Qwen 연결 금지
Fake Lightroom 통과 전 실제 Lightroom Lua Plugin 연결 금지
Smoke Pipeline 통과 전 기능 완료 처리 금지
Security Harness 통과 전 실제 모델 backend 활성화 금지
Loop Event 검증 전 자동 에이전트 루프 완료 처리 금지
```

## 포함된 하네스

| Harness | 파일 | 목적 |
|---|---|---|
| Runtime Reset | `harness/scripts/reset_runtime.py` | `runtime/` 테스트 폴더 초기화 |
| Metadata/Preview | `harness/scripts/run_metadata_preview_test.py` | EXIF 추출과 1024px preview artifact 검증 |
| Mock Vision | `harness/scripts/run_vision_mock_test.py` | mock vision schema, raw/structured artifact 검증 |
| Correction Planner | `harness/scripts/run_correction_planner_test.py` | clamping, requires_review, plan artifact 검증 |
| Fake Lightroom Worker | `harness/fake_lightroom/fake_lightroom_worker.py` | Lightroom request JSON을 읽고 fake export/response 생성 |
| Fake Lightroom Bridge | `harness/scripts/run_fake_lightroom_test.py` | JSON bridge request/response, absolute path 계약 검증 |
| Quality Gate | `harness/scripts/run_quality_gate_test.py` | quality score, sticky review, final decision 검증 |
| Worker Pipeline | `harness/scripts/run_worker_pipeline_test.py` | worker stage commit 순서와 단일 사진 처리 흐름 검증 |
| Smoke Pipeline | `harness/scripts/run_smoke_pipeline.py` | 사진 1장 end-to-end MVP 파이프라인 검증 |
| Recovery | `harness/scripts/run_recovery_test.py` | 중간 실패/재시작 복구 시나리오 검증 |
| Security | `harness/scripts/run_security_check.py` | 로컬 모델 보안 금지 패턴과 offline 계약 정적/동작 검사 |
| Watcher | `harness/scripts/run_watcher_test.py` | 파일 감지, 안정화, 무시, dedupe 검증 |
| Artifact Verify | `harness/scripts/verify_artifacts.py` | 필수 artifact 존재, checksum, DB 등록 검증 |
| DB State Verify | `harness/scripts/verify_db_state.py` | PostgreSQL task/stage/quality/event 상태 검증 |
| CLI Verify | `harness/scripts/verify_cli_operations.py` | CLI 명령과 서비스 계층 연결 검증 |
| Lightroom Plugin PoC | `harness/scripts/verify_lightroom_plugin_poc.py` | 최소 Lightroom plugin PoC와 bridge 호환성 검증 |
| Loop Events | `harness/scripts/verify_loop_events.py` | task_events에 product loop evidence가 남는지 검증 |
| Feedback Learning | `harness/scripts/verify_feedback_learning.py` | local-only feedback capture와 learning sample 준비 검증 |
| Model Benchmark | `harness/scripts/run_model_benchmark_test.py` | bounded benchmark loop와 default backend 비승격 검증 |
| Qwen Backend Guard | `harness/scripts/run_qwen_backend_test.py` | 실제 Qwen backend 연결 전 local-only guard 검증 |

## 권장 실행 순서

초기 개발 단계에서는 작은 단위에서 큰 단위로 검증합니다.

```powershell
python harness/scripts/reset_runtime.py
python harness/scripts/run_metadata_preview_test.py
python harness/scripts/run_vision_mock_test.py
python harness/scripts/run_correction_planner_test.py
python harness/scripts/run_fake_lightroom_test.py
python harness/scripts/run_quality_gate_test.py
python harness/scripts/run_worker_pipeline_test.py
python harness/scripts/run_smoke_pipeline.py
python harness/scripts/run_recovery_test.py
python harness/scripts/run_security_check.py
python harness/scripts/verify_loop_events.py
python harness/scripts/verify_feedback_learning.py
python harness/scripts/verify_cli_operations.py
```

`run_smoke_pipeline.py`와 일부 verify 스크립트는 프로젝트 코드의 CLI, DB 모델, worker가 구현된 뒤 통과합니다. 초기에는 **실패하는 것이 정상**이며, 실패 메시지를 기준으로 구현 티켓을 작게 나눕니다.

## 환경 변수

`.env` 또는 PowerShell 환경 변수로 아래 값을 사용합니다.

```env
TONEVYRA_ENV=harness
TONEVYRA_RUNTIME_DIR=runtime
TONEVYRA_INPUT_DIR=runtime/input
TONEVYRA_OUTPUT_DIR=runtime/output
TONEVYRA_ARTIFACT_DIR=runtime/artifacts
TONEVYRA_PREVIEW_DIR=runtime/previews
TONEVYRA_BRIDGE_DIR=runtime/bridge
TONEVYRA_LOG_DIR=logs
TONEVYRA_MODELS_DIR=models
TONEVYRA_VISION_BACKEND=mock
TONEVYRA_LIGHTROOM_BACKEND=fake
TONEVYRA_MODEL_OFFLINE=true
TONEVYRA_WORKER_CONCURRENCY=1
TONEVYRA_HARNESS_AGENT_COMMAND=python -m tonevyra_agent.cli start
```

오프라인 모델 보안 환경 변수도 하네스 기본값에 포함합니다.

```env
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
```

프로젝트 CLI가 아직 없으면 `TONEVYRA_HARNESS_AGENT_COMMAND`는 나중에 설정합니다.

## 프로젝트에 붙이는 법

이 폴더를 프로젝트 루트에 그대로 복사합니다.

```text
tonevyra_agent/
  AGENTS.md
  CLAUDE.md
  skills/
  harness/
  tests/
  src/
    tonevyra_agent/
```

Claude/Codex에게 작업시킬 때는 아래처럼 지시합니다.

```text
Read AGENTS.md first.
Then read skills/project-scope/SKILL.md, skills/testing-harness/SKILL.md,
skills/python-mvp-structure/SKILL.md, and skills/agent-worker-pipeline/SKILL.md.
Implement the mock smoke pipeline so harness/scripts/run_smoke_pipeline.py passes.
Do not connect real Qwen.
Do not connect real Lightroom.
Do not add scope outside the listed skills.
```

## Loop Engineering Verification

이 하네스는 파일 존재만 보지 않고, 제품 루프가 실제로 구현되었는지 확인합니다.

Required product loops:

```text
watch_loop
processing_loop
quality_loop
recovery_loop
feedback_loop
model_benchmark_loop
```

MVP smoke harness는 최소한 processing loop가 final state에 도달하고, quality loop가 PASS / REVIEW_REQUIRED / FAILED 중 하나를 결정하며, recovery loop가 안전하게 재개 또는 실패 처리할 수 있음을 증명해야 합니다.

Additional scripts:

```powershell
python harness/scripts/verify_loop_events.py
python harness/scripts/verify_feedback_learning.py
```

`verify_loop_events.py`는 PostgreSQL task_events에 loop evidence가 있는지 확인합니다. `verify_feedback_learning.py`는 local-only feedback-learning schema, artifact, approval flag, learning sample 준비 상태를 확인합니다.
