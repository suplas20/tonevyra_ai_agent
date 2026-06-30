# T-031 Windows VRAM Live Test Checklist

## 환경 기록

```text
Windows version/build:
GPU/VRAM:
NVIDIA driver:
Tonevyra build SHA-256:
Model revision/quantization:
idle grace seconds:
```

## 테스트

- [ ] Shell/Watcher 시작 직후 모델 Worker가 존재하지 않는다.
- [ ] 작업 등록 시 Worker가 하나만 시작된다.
- [ ] 작업 중 모델 VRAM 사용량이 기록된다.
- [ ] 큐가 비면 IDLE_GRACE로 전환된다.
- [ ] grace 만료 후 Worker 프로세스가 종료된다.
- [ ] 종료 후 Tonevyra 전용 VRAM이 기준치 이하로 내려간다.
- [ ] 다음 작업에서 Worker와 모델이 정상 재기동된다.
- [ ] 10회 load/process/unload 반복 후 orphan PID가 없다.
- [ ] Lightroom GPU 작업과 동시에 무한 점유하지 않는다.

## 필수 첨부

```text
windows_vram_live_evidence.json
nvidia_smi_idle_before.csv
nvidia_smi_loaded.csv
nvidia_smi_post_unload.csv
worker_lifecycle.log
```
