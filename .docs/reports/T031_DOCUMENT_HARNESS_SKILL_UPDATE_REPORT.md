# T-031 문서·하네스·스킬 업데이트 보고서

## 업데이트 요약

T-030 기준 45개 스킬을 모두 유지하고 다음 2개를 추가했다.

```text
macos-apple-silicon-runtime
inference-worker-memory-lifecycle
```

총 스킬 수는 47개다.

## 핵심 설계

```text
- 공통 Core와 OS adapter 분리
- Apple Silicon arm64/macOS 13+ 우선
- macOS menu bar + FSEvents + Login Item + MPS
- Shell/Watcher와 Inference Worker 프로세스 분리
- lazy model load
- bounded idle grace
- Worker 종료 기반 VRAM/GPU context 반환
- Windows VRAM live gate와 macOS live gate 분리
```

## 중요한 완료 조건

정적 계약 및 reference runtime 통과만으로 T-031 완료를 선언할 수 없다.

```text
BLOCKED_MACOS_LIVE_EVIDENCE_MISSING
BLOCKED_WINDOWS_VRAM_EVIDENCE_MISSING
```

두 live gate를 실제 장비에서 통과해야 strict completion이다.
