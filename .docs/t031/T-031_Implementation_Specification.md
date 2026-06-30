# T-031 구현 명세

## 1. 권장 모듈 구조

```text
tonevyra_agent/
├─ platform/
│  ├─ contracts.py
│  ├─ factory.py
│  ├─ windows/
│  └─ macos/
├─ inference/
│  ├─ worker_process.py
│  ├─ lifecycle.py
│  ├─ memory_telemetry.py
│  └─ backends/
│     ├─ cuda_backend.py
│     └─ mps_backend.py
└─ shell/
   ├─ windows_tray/
   └─ macos_menu_bar/
```

## 2. 필수 인터페이스

```python
class PlatformRuntime(Protocol):
    def acquire_single_instance(self) -> None: ...
    def create_folder_watcher(self, roots: list[str]): ...
    def register_login_start(self, enabled: bool) -> None: ...
    def open_path(self, path: str) -> None: ...
    def check_folder_access(self, path: str, write: bool = False): ...

class InferenceWorkerController(Protocol):
    def ensure_started(self) -> None: ...
    def submit(self, job_id: str, payload_path: str): ...
    def mark_activity(self) -> None: ...
    def stop_after_idle(self) -> None: ...
    def force_stop(self) -> None: ...
```

## 3. 프로세스 경계

```text
Shell process
- menu/tray UI
- no torch import
- no model loading

Agent process
- watcher, queue, supervisor
- no persistent model object

Inference Worker process
- torch/MLX import
- model load
- one-job-at-a-time inference
- exits after idle timeout
```

## 4. idle unload 알고리즘

```text
on queue transition empty:
  record monotonic last_activity
  enter IDLE_GRACE

periodic supervisor tick:
  if queue non-empty: cancel unload
  if active request: do nothing
  if now-last_activity >= idle_grace:
      request graceful worker shutdown
      wait bounded timeout
      terminate only if graceful stop fails
      verify process exit
      capture post-exit memory evidence
```

모델 객체를 CPU로 이동하고 `empty_cache()`만 호출한 상태를 `UNLOADED`로 기록하지 않는다.

## 5. 설정

```text
TONEVYRA_INFERENCE_IDLE_GRACE_SECONDS=300
TONEVYRA_KEEP_MODEL_WARM=false
TONEVYRA_MAX_INFERENCE_WORKERS=1
TONEVYRA_MACOS_BACKEND=mps
TONEVYRA_ALLOW_CPU_FALLBACK=false
TONEVYRA_MEMORY_RELEASE_THRESHOLD_MB=512
```

## 6. live evidence

macOS evidence:

```text
OS/build, chip, memory, app arch
menu bar screenshots
FSEvents ingest logs
MPS backend probe
Lightroom bridge result
10-image soak memory series
```

Windows evidence:

```text
GPU name/driver
worker PID
idle-before, loaded, post-job, post-timeout VRAM
nvidia-smi process evidence
no duplicate worker
```

## 7. 금지 구현

```text
- Shell process에서 torch import
- app startup에서 eager model load
- 무한 keep-warm 기본값
- orphan child process
- CPU fallback 숨김
- macOS 권한 실패를 일반 파일 없음으로 처리
- FSEvents event 1개를 곧바로 1 job으로 변환
```
