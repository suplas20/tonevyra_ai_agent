# Skill: Inference Worker Memory Lifecycle

## 목적

백그라운드 감시는 유지하면서 작업이 없을 때 CUDA/MPS 모델과 GPU 컨텍스트를 장시간 점유하지 않도록 추론 Worker의 생성·유예·종료를 관리한다.

## 핵심 규칙

```text
- Shell/Watcher는 모델을 로딩하지 않는다.
- Worker는 durable queue에 작업이 있을 때 lazy start한다.
- Worker 동시성은 1이다.
- 마지막 작업 후 bounded idle grace를 적용한다.
- grace 만료 시 Worker 프로세스를 종료한다.
- empty_cache()만으로 UNLOADED를 기록하지 않는다.
- 종료 PID와 post-unload memory evidence를 남긴다.
```

## 구현 절차

```text
1. 현재 모델 소유 PID와 eager load 지점을 찾는다.
2. 모델 runtime을 child process 경계로 이동한다.
3. supervisor에 heartbeat와 monotonic idle timer를 추가한다.
4. queue non-empty 시 unload를 취소한다.
5. graceful shutdown 후 bounded wait를 적용한다.
6. 실패 시 강제 종료하고 오류 evidence를 남긴다.
7. 10회 load/process/unload 반복 테스트를 수행한다.
8. Windows nvidia-smi와 macOS process memory로 실기기 검증한다.
```

## 실패 판정

```text
INFERENCE_WORKER_DUPLICATE
INFERENCE_WORKER_IDLE_UNLOAD_FAILED
GPU_MEMORY_NOT_RELEASED
ORPHAN_INFERENCE_PROCESS
```
