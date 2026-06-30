# T-031 Codex 실행 프롬프트

당신은 Tonevyra AI Agent 저장소에서 T-031을 구현한다.

## 시작 전 필수 읽기

```text
AGENTS.md
CLAUDE.md
.docs/t031/T-031_macOS_Apple_Silicon_Runtime_and_Idle_VRAM_Work_Order.md
.docs/t031/T-031_Implementation_Specification.md
harness/CONTRACT_T031_MACOS_RUNTIME_GPU_LIFECYCLE.md
skills/macos-apple-silicon-runtime/SKILL.md
skills/inference-worker-memory-lifecycle/SKILL.md
skills/testing-harness/SKILL.md
```

## 구현 순서

```text
Phase 0: 현재 eager model load/VRAM owner PID를 증거로 확인
Phase 1: PlatformRuntime와 OS adapter 경계 도입
Phase 2: Inference Worker를 별도 프로세스로 분리
Phase 3: lazy start + bounded idle unload 구현
Phase 4: CUDA memory telemetry와 Windows live probe
Phase 5: macOS arm64 runtime, FSEvents, menu bar, login item
Phase 6: MPS model probe와 one-photo pipeline
Phase 7: Windows 회귀와 macOS/VRAM live evidence
```

## 하드 규칙

```text
- T-030 Windows 기능을 깨지 않는다.
- Shell/Watcher에서 모델을 로딩하지 않는다.
- 모델 Worker 동시성은 1이다.
- empty_cache()만으로 unload 성공을 선언하지 않는다.
- Worker 프로세스 종료를 최종 해제 경계로 사용한다.
- macOS live evidence 없이 macOS 완료를 선언하지 않는다.
- nvidia-smi 또는 동등한 process evidence 없이 VRAM gate 통과를 선언하지 않는다.
- CPU fallback을 숨기지 않는다.
- 런타임 모델 다운로드를 추가하지 않는다.
```

## 완료 보고

한국어로 다음을 보고한다.

```text
변경 파일
실행 명령
정적 harness 결과
reference runtime 결과
Windows VRAM live 결과
macOS live 결과
남은 BLOCKED 상태
회귀 테스트 결과
```
