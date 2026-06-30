# T-031 — macOS Apple Silicon Runtime and Idle GPU Memory Lifecycle 작업 지시서

## 1. 문서 상태

```text
Ticket: T-031
Title: macOS Apple Silicon Runtime and Idle GPU Memory Lifecycle
Baseline: T-030 Windows Background Watcher and System Tray Agent
Primary macOS target: Apple Silicon arm64, macOS 13+
Reference device: M1-class MacBook, unified memory 32GB
Windows regression target: Windows 10/11 x64 + NVIDIA CUDA
Depends on: T-022 model provider, T-028 reliability, T-030 background agent
```

## 2. 목표

> 동일한 Tonevyra Core가 Windows와 macOS에서 동작하도록 플랫폼 경계를 분리하고, macOS에서는 메뉴 막대 앱·FSEvents·Login Item·Apple GPU backend를 제공하며, Windows와 macOS 모두 작업이 없을 때 추론 Worker가 GPU 메모리를 장시간 점유하지 않도록 명시적인 모델 수명주기를 구현한다.

## 3. 핵심 결과

```text
공통 Core
├─ 작업 큐·상태 머신·복구·중복 방지
├─ Lightroom bridge contract
├─ 모델 요청/응답 contract
└─ idle inference lifecycle policy

Windows Adapter
├─ system tray
├─ Windows watcher/startup/single-instance
└─ CUDA backend

macOS Adapter
├─ menu bar status item
├─ FSEvents watcher
├─ SMAppService login item
├─ POSIX paths/permissions
└─ MPS first, optional MLX candidate
```

## 4. 필수 구현 범위

```text
- PlatformRuntime 인터페이스와 Windows/macOS adapter 분리
- arm64 네이티브 macOS Worker
- macOS 메뉴 막대 Shell
- macOS 단일 인스턴스와 Worker heartbeat
- FSEvents 기반 폴더 감시 + 기존 안정화/중복 방지 재사용
- 사용자 선택 폴더 권한과 명시적 오류 처리
- Lightroom Classic macOS 플러그인 경로 지원
- PyTorch MPS 1차 backend
- CPU fallback은 명시적 degraded mode에서만 허용
- 추론 Worker lazy start
- 작업 종료 후 bounded idle grace
- idle timeout 후 Worker 종료와 GPU/unified-memory 반환
- CUDA/MPS 메모리 telemetry
- Windows T-030 회귀 방지
- macOS live evidence와 Windows VRAM live evidence
```

## 5. 제외 범위

```text
- Intel Mac / Universal 2 출시 보장
- Mac App Store 배포
- 전체 모델 런타임 MLX 재작성
- 다중 GPU 또는 다중 추론 Worker
- Windows Service / macOS privileged daemon
- UI 좌표 자동화
- 무제한 CPU fallback
- 실행 중 자동 모델 다운로드
- 임의 XMP 조작
```

## 6. 플랫폼 경계

공통 코드에 운영체제 분기문을 산재시키지 않는다. 다음 인터페이스 뒤로 격리한다.

```text
PlatformRuntime
FolderWatcher
StartupRegistration
StatusSurface
SingleInstanceGuard
PathProvider
PermissionBroker
InferenceBackend
MemoryTelemetry
```

## 7. macOS 상태 UI

Windows tray에 대응하는 UI는 macOS 메뉴 막대 `NSStatusItem`이다.

```text
- 컬러 앱 아이콘: .icns
- 메뉴 막대 아이콘: monochrome template asset
- 메뉴: 상태, 처리/대기/실패 수, 대시보드, 폴더 열기,
  감시 일시정지/재개, 재검색, Worker 재시작, 로그, 종료
- Shell은 비즈니스 로직을 소유하지 않음
```

아이콘 원본이 없거나 template asset이 검증되지 않으면:

```text
BLOCKED_MACOS_ICON_ASSET_MISSING
```

## 8. macOS 폴더 감시

FSEvents는 변경 힌트로 취급한다. 이벤트 자체를 작업 생성의 단독 근거로 사용하지 않는다.

```text
FSEvents notification
→ affected root rescan
→ extension/filter
→ debounce
→ size/mtime/read probe stability
→ dedup identity
→ PostgreSQL registration
```

## 9. AI backend 정책

### 9.1 MPS first

```text
- torch.backends.mps.is_available() 검증
- model load smoke
- single-image inference
- schema validation
- 10-image soak
- no silent CPU fallback
```

MPS에서 필수 연산이 지원되지 않으면 다음 상태로 중단한다.

```text
BLOCKED_MPS_OPERATOR_UNSUPPORTED
```

### 9.2 MLX

MLX는 별도 benchmark를 통과한 경우에만 후보 backend로 추가한다. T-031 완료에 필수는 아니다.

## 10. 추론 Worker와 GPU 메모리 수명주기

항상 실행되는 Shell/Watcher는 모델을 로딩하지 않는다.

```text
UNLOADED
→ job available
→ STARTING
→ LOADING
→ READY
→ PROCESSING
→ IDLE_GRACE
→ STOPPING
→ UNLOADED
```

기본 정책:

```text
max_inference_workers = 1
idle_grace_seconds = 300
keep_warm_mode = false
```

규칙:

```text
- 작업이 없으면 Worker를 시작하지 않음
- 마지막 작업 후 grace 동안만 모델 유지
- grace 만료 시 Worker 프로세스 종료
- 프로세스 종료를 VRAM 반환의 1차 보장 수단으로 사용
- empty_cache()만으로 unload 성공을 선언하지 않음
- Worker 종료 후 orphan CUDA/MPS process 금지
```

## 11. 메모리 telemetry

Windows CUDA:

```text
allocated_bytes
reserved_bytes
nvidia_process_used_bytes (가능한 경우)
worker_pid
```

macOS:

```text
resident_memory_bytes
system memory pressure
swap delta
backend=mps|cpu|mlx
worker_pid
```

민감한 프롬프트나 모델 출력은 telemetry에 기록하지 않는다.

## 12. 오류 코드

```text
BLOCKED_MACOS_ARM64_BUILD
BLOCKED_MACOS_ICON_ASSET_MISSING
BLOCKED_MACOS_LIGHTROOM_BRIDGE
BLOCKED_MPS_MODEL_LOAD
BLOCKED_MPS_OPERATOR_UNSUPPORTED
MACOS_INPUT_FOLDER_PERMISSION_DENIED
MACOS_OUTPUT_FOLDER_PERMISSION_DENIED
INFERENCE_WORKER_START_FAILED
INFERENCE_WORKER_IDLE_UNLOAD_FAILED
INFERENCE_WORKER_DUPLICATE
GPU_MEMORY_NOT_RELEASED
```

## 13. 하드 게이트

```text
GATE-01 arm64 native process, no Rosetta requirement
GATE-02 menu bar icon and allowlisted menu commands live
GATE-03 FSEvents + stability + dedup live
GATE-04 MPS model load and one real image analysis
GATE-05 Lightroom macOS bridge one-photo end-to-end
GATE-06 10-photo sequential soak without monotonic memory growth
GATE-07 idle start uses negligible model VRAM/unified GPU memory
GATE-08 idle timeout terminates Worker
GATE-09 Windows CUDA Worker exit releases process VRAM below threshold
GATE-10 duplicate Worker prohibited
GATE-11 restart restores durable queue
GATE-12 Windows T-030 regression suite passes
GATE-13 signed arm64 app evidence before release claim
GATE-14 notarization evidence before public distribution claim
```

## 14. 완료 판정

정적 계약과 mock/reference runtime만 통과한 상태는 완료가 아니다.

```text
READY_FOR_MACOS_LIVE_TEST
READY_FOR_WINDOWS_VRAM_LIVE_TEST
```

실기기 증거가 없으면 다음과 같이 보고한다.

```text
BLOCKED_MACOS_LIVE_EVIDENCE_MISSING
BLOCKED_WINDOWS_VRAM_EVIDENCE_MISSING
```
