# MW Photo Correction Agent — Harness

이 `harness/` 폴더는 MW Photo Correction Agent MVP를 **실제 Qwen 모델 / 실제 Lightroom Classic 없이 검증**하기 위한 실행 하네스입니다.

## 핵심 원칙

```text
Mock Vision 통과 전 실제 Qwen 연결 금지
Fake Lightroom 통과 전 실제 Lightroom Lua Plugin 연결 금지
Smoke Pipeline 통과 전 기능 완료 처리 금지
```

## 포함된 하네스

| Harness | 파일 | 목적 |
|---|---|---|
| Runtime Reset | `harness/scripts/reset_runtime.py` | `runtime/` 테스트 폴더 초기화 |
| Fake Lightroom | `harness/fake_lightroom/fake_lightroom_worker.py` | Lightroom request JSON을 읽고 fake export/response 생성 |
| Smoke Pipeline | `harness/scripts/run_smoke_pipeline.py` | 사진 1장 end-to-end 파이프라인 검증 |
| Recovery | `harness/scripts/run_recovery_test.py` | 중간 실패/재시작 복구 시나리오 검증용 드라이버 |
| Security | `harness/scripts/run_security_check.py` | 모델 보안 금지 패턴 정적 검사 |
| Watcher | `harness/scripts/run_watcher_test.py` | 파일 감지/무시/중복 등록 흐름 검증용 드라이버 |
| Artifact Verify | `harness/scripts/verify_artifacts.py` | 필수 artifact 존재 여부 검증 |

## 권장 실행 순서

초기 개발 단계에서는 아래 순서로 하네스를 도입합니다.

```powershell
python harness/scripts/reset_runtime.py
python harness/fake_lightroom/fake_lightroom_worker.py --once
python harness/scripts/run_smoke_pipeline.py
python harness/scripts/run_security_check.py
```

단, `run_smoke_pipeline.py`는 프로젝트 코드의 CLI 또는 worker가 구현된 뒤 통과합니다. 초기에는 **실패하는 것이 정상**이며, 이 실패 메시지를 기준으로 Codex/Claude에게 구현을 맡기면 됩니다.

## 환경 변수

`.env` 또는 PowerShell 환경 변수로 아래 값을 사용합니다.

```env
MW_ENV=harness
VISION_BACKEND=mock
LIGHTROOM_BACKEND=fake
MODEL_OFFLINE=true
WORKER_CONCURRENCY=1
MW_RUNTIME_DIR=runtime
MW_HARNESS_AGENT_COMMAND=python -m mw_photo_agent.cli start --once
```

프로젝트 CLI가 아직 없으면 `MW_HARNESS_AGENT_COMMAND`는 나중에 설정합니다.

## 프로젝트에 붙이는 법

이 폴더를 프로젝트 루트에 그대로 복사합니다.

```text
mw_photo_agent/
  AGENTS.md
  CLAUDE.md
  skills/
  harness/
  tests/
  src/
```

Claude/Codex에게 작업시킬 때는 아래처럼 지시합니다.

```text
Read AGENTS.md first.
Then read skills/testing-harness/SKILL.md, skills/python-mvp-structure/SKILL.md, and skills/agent-worker-pipeline/SKILL.md.
Implement the mock smoke pipeline so harness/scripts/run_smoke_pipeline.py passes.
Do not connect real Qwen.
Do not connect real Lightroom.
```


## Loop Engineering Verification

This harness now verifies the product loops, not only file existence.

Required product loops:

```text
watch_loop
processing_loop
quality_loop
recovery_loop
feedback_loop
model_benchmark_loop
```

The MVP smoke harness should prove that the processing loop reaches a final state, that the quality loop produces a decision, and that recovery loop scenarios can resume or fail safely.

Additional scripts:

```powershell
python harness/scripts/verify_loop_events.py
python harness/scripts/verify_feedback_learning.py
```

`verify_loop_events.py` checks that PostgreSQL task events contain loop evidence. `verify_feedback_learning.py` checks that the project has a local-only feedback-learning schema or explicitly staged placeholders.
