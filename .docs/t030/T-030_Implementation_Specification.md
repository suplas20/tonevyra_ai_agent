# T-030 구현 명세 — Windows Background Watcher와 System Tray Agent

## 1. 목적

이 문서는 T-030 작업 지시서를 실제 Python 모듈, 프로세스 경계, IPC, 데이터 모델, 상태 전이, 설정, 테스트와 하네스로 변환한다. 동일 책임의 구현이 이미 있으면 새 구조를 병렬로 만들지 말고 기존 코드를 확장한다.

## 2. 구현 원칙

```text
- Tray는 얇은 UI shell이다.
- Worker가 watcher와 pipeline을 소유한다.
- PostgreSQL이 영속 작업 큐의 source of truth이다.
- 파일 이벤트는 신뢰하지 않고 안정화 후 처리한다.
- 동일 사진은 exactly-once effect에 가깝게 처리한다.
- 종료와 crash는 checkpoint/recovery 경계를 사용한다.
- Windows 사용자 세션 앱이며 Service가 아니다.
```

## 3. 권장 패키지 구조

```text
src/tonevyra_agent/
  agent/
    background_runtime.py
    lifecycle.py
    runtime_state.py
    runtime_snapshot.py

  watcher/
    folder_watcher.py
    event_coalescer.py
    file_stability.py
    file_identity.py
    exclusion_policy.py
    rescan.py

  windows/
    tray_shell.py
    tray_menu.py
    tray_state.py
    tray_icons.py
    single_instance.py
    startup_registration.py
    shell_worker_ipc.py
    worker_supervisor.py
    session_events.py

  db/
    repositories.py

  cli.py

resources/branding/
  source/tonevyra_symbol.svg
  windows/tonevyra_tray.ico
  windows/tonevyra_tray_processing.ico
  windows/tonevyra_tray_warning.ico
  windows/tonevyra_tray_error.ico
```

실제 브랜딩 원본 경로는 프로젝트 구조에 맞춰 조정할 수 있다. 화면 캡처를 icon source로 저장하지 않는다.

## 4. 프로세스 모델

### 4.1 Tray Shell

```python
class TrayShell(Protocol):
    def run(self) -> int: ...
    def request_shutdown(self) -> None: ...
    def update_snapshot(self, snapshot: "AgentRuntimeSnapshot") -> None: ...
```

책임:

```text
- named mutex
- tray icon lifecycle
- menu rendering
- IPC client
- worker supervision
- user notifications
- dashboard/status screen launch
```

### 4.2 Background Worker

```python
class BackgroundAgentRuntime(Protocol):
    def start(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def rescan(self) -> None: ...
    def shutdown(self, timeout_seconds: float) -> None: ...
    def snapshot(self) -> "AgentRuntimeSnapshot": ...
```

책임:

```text
- Watcher
- stabilization
- task registration
- processing loop
- recovery
- runtime snapshot
- heartbeat
```

### 4.3 실행 모드

기존 entrypoint를 유지하며 다음 모드를 추가하는 방식이 권장된다.

```text
tonevyra-agent background
tonevyra-agent tray
tonevyra-agent status
tonevyra-agent watch pause
tonevyra-agent watch resume
tonevyra-agent watch rescan
tonevyra-agent startup enable
tonevyra-agent startup disable
tonevyra-agent startup status
```

패키징 시 이 entrypoint를 별도 EXE 또는 동일 EXE의 mode로 구성할 수 있다.

## 5. AgentRuntimeSnapshot

```json
{
  "schema_version": "t030.agent_runtime_snapshot.v1",
  "agent_instance_id": "agent-uuid",
  "shell_instance_id": "shell-uuid",
  "state": "WATCHING",
  "started_at": "2026-06-29T10:00:00Z",
  "last_heartbeat_at": "2026-06-29T10:00:05Z",
  "watching_enabled": true,
  "watch_path": "D:\\Tonevyra\\Input",
  "recursive": false,
  "queue_depth": 0,
  "processing_count": 0,
  "failed_count": 0,
  "active_job_id": null,
  "lightroom_connected": true,
  "model_ready": true,
  "db_ready": true,
  "degraded_reasons": [],
  "worker_restart_count": 0,
  "version": "0.30.0"
}
```

Validation:

```text
- runtime state는 T-030 enum만 허용
- queue/processing/failed count는 0 이상
- PROCESSING이면 active_job_id 또는 processing_count > 0
- DEGRADED이면 degraded_reasons가 비어 있지 않음
- STOPPED이면 watching_enabled=false
```

## 6. WatchCandidate

```json
{
  "schema_version": "t030.watch_event.v1",
  "event_id": "watch-event-uuid",
  "event_type": "CREATED",
  "observed_path": "D:\\Tonevyra\\Input\\photo.cr3",
  "normalized_path": "d:\\tonevyra\\input\\photo.cr3",
  "first_seen_at": "2026-06-29T10:00:00Z",
  "last_seen_at": "2026-06-29T10:00:04Z",
  "coalesced_event_count": 4,
  "stability": {
    "sample_count": 3,
    "stable_samples": 3,
    "size_bytes": 42000000,
    "mtime_ns": 1782700000000000000,
    "read_probe_passed": true
  },
  "identity": {
    "size_bytes": 42000000,
    "mtime_ns": 1782700000000000000,
    "source_hash": "sha256-or-null-before-full-hash"
  },
  "decision": "QUEUE"
}
```

`event_type`:

```text
CREATED
MODIFIED
RENAMED
MOVED_IN
RESCAN_DISCOVERED
```

`decision`:

```text
WAIT_STABLE
QUEUE
IGNORE_TEMPORARY
IGNORE_EXCLUDED
IGNORE_DUPLICATE
SKIP_UNSUPPORTED
FAIL_STABILIZATION
```

## 7. Event Coalescer

```python
class EventCoalescer:
    def ingest(self, event: RawWatchEvent) -> None: ...
    def pop_ready(self, now: datetime) -> list[CoalescedWatchEvent]: ...
```

규칙:

```text
- normalized path를 key로 사용
- event마다 debounce deadline을 갱신
- rename은 old/new 경로를 연결
- 같은 파일의 Modified 폭주가 새 task를 만들지 않음
- 최대 보관 수와 TTL을 설정
- pause 중 무제한 메모리 큐를 만들지 않음
```

## 8. File Stability Gate

```python
class FileStabilityChecker:
    def wait_until_stable(
        self,
        path: Path,
        policy: StabilityPolicy,
        cancellation: CancellationToken,
    ) -> FileStabilityResult: ...
```

`StabilityPolicy`:

```json
{
  "interval_seconds": 2.0,
  "required_stable_samples": 3,
  "timeout_seconds": 300.0,
  "minimum_size_bytes": 1,
  "require_read_probe": true
}
```

안정 샘플은 `size_bytes`와 `mtime_ns`가 이전 샘플과 같을 때만 증가한다. 파일이 사라지거나 rename되면 candidate identity를 재평가한다.

Windows에서 독점 lock 여부만으로 준비 상태를 결정하지 않는다. 카메라/동기화 도구가 공유 읽기를 허용할 수 있기 때문이다.

## 9. Exclusion Policy

```python
class WatchExclusionPolicy:
    def classify(self, path: Path, config: WatchConfig) -> ExclusionDecision: ...
```

검사 순서:

```text
1. hidden/system/internal file
2. temp/partial extension
3. internal runtime/cache/output/failed folder
4. unsupported extension
5. source/output recursion
6. supported candidate
```

Path 비교는 `resolve(strict=False)`와 Windows case-insensitive normalized form을 사용한다. symlink/junction 재귀도 고려한다.

## 10. File Identity와 DB idempotency

```python
@dataclass(frozen=True)
class FileIdentity:
    normalized_path: str
    size_bytes: int
    mtime_ns: int
    source_hash: str | None
```

Repository API:

```python
class WatchedTaskRepository(Protocol):
    def register_or_get_existing(
        self,
        identity: FileIdentity,
        detected_at: datetime,
        watch_event_id: str,
    ) -> TaskRegistrationResult: ...
```

`register_or_get_existing()`는 transaction 안에서 동작한다. race가 발생해도 외부 pipeline 실행은 한 번만 시작해야 한다.

## 11. Rescan

Watcher 시작, resume, overflow, 사용자 명령 시 bounded rescan을 수행한다.

```text
- 지정 폴더만 탐색
- recursive 설정 존중
- 최대 파일 수/시간 budget
- newest-first 또는 deterministic path order
- 각 파일에 동일 exclusion/stability/dedup 정책 적용
- watchdog event와 rescan result를 합쳐도 중복 task 없음
```

Filesystem watcher overflow가 발생하면 조용히 누락하지 않고 incident를 남기고 rescan한다.

## 12. Runtime State Reducer

상태는 임의 setter가 아니라 입력 상태를 기반으로 계산한다.

우선순위 예:

```text
fatal_error → ERROR
shutdown_requested → STOPPING
watch_paused → PAUSED
dependency_failure but process alive → DEGRADED
active job exists → PROCESSING
initialized → WATCHING
else → STARTING
```

Tray는 reducer 결과를 표시한다. Tray 자체 판단으로 `PROCESSING`을 만들지 않는다.

## 13. Tray State Mapping

```json
{
  "WATCHING": "tonevyra_tray.ico",
  "PROCESSING": "tonevyra_tray_processing.ico",
  "PAUSED": "tonevyra_tray_warning.ico",
  "DEGRADED": "tonevyra_tray_warning.ico",
  "ERROR": "tonevyra_tray_error.ico"
}
```

`STARTING`, `STOPPING`, `STOPPED`는 tooltip/menu text와 fallback icon 정책을 명시한다.

Tooltip 예:

```text
Tonevyra AI — 감시 중
Tonevyra AI — 2장 처리 중, 8장 대기
Tonevyra AI — 감시 일시정지
Tonevyra AI — Lightroom 연결 대기
Tonevyra AI — 오류 확인 필요
```

## 14. Tray Command Envelope

```json
{
  "schema_version": "t030.tray_command.v1",
  "command_id": "command-uuid",
  "command": "PAUSE_WATCHING",
  "requested_at": "2026-06-29T10:01:00Z",
  "source": "TRAY",
  "expected_agent_instance_id": "agent-uuid"
}
```

Response:

```json
{
  "command_id": "command-uuid",
  "status": "APPLIED",
  "agent_state": "PAUSED",
  "idempotent_replay": false,
  "error_code": null
}
```

허용 status:

```text
APPLIED
NO_OP
REJECTED
FAILED
```

동일 `command_id` 재전송은 외부 효과를 중복 실행하지 않는다.

## 15. IPC 보안과 안정성

```text
- 사용자별 named pipe name
- 현재 사용자 SID 기반 ACL
- payload size limit
- schema validation
- request timeout
- nonce/request ID
- command allowlist
- no arbitrary shell command
- no file path execution command
```

Tray에서 `OPEN_INPUT_FOLDER` 같은 UI 명령은 검증된 configured path만 사용한다.

## 16. Worker Supervision

```python
class WorkerSupervisor:
    def ensure_running(self) -> WorkerHandle: ...
    def observe_heartbeat(self, snapshot: AgentRuntimeSnapshot) -> None: ...
    def restart_if_allowed(self, reason: str) -> RestartDecision: ...
```

정책 예:

```json
{
  "heartbeat_timeout_seconds": 20,
  "restart_window_seconds": 300,
  "maximum_restarts_in_window": 3,
  "restart_backoff_seconds": [2, 5, 15]
}
```

restart limit 초과 시 `WORKER_CRASH_LOOP`와 `ERROR`로 전환한다.

## 17. Startup Registration

T-030 구현은 등록 abstraction과 CLI를 제공한다. 실제 설치 프로그램은 후속 티켓에서 호출한다.

기본 사용자 범위:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

등록 value는 제품 패키징 후 확정된 실행 파일과 `--tray` 인자를 사용한다. 개발 환경 absolute Python path를 release 등록값으로 남기지 않는다.

API:

```python
class StartupRegistration(Protocol):
    def enable(self, executable: Path, args: Sequence[str]) -> None: ...
    def disable(self) -> None: ...
    def status(self) -> StartupStatus: ...
```

## 18. Graceful Shutdown

```python
async def shutdown(timeout: float) -> ShutdownResult:
    # 1. intake stop
    # 2. watcher close
    # 3. current stage checkpoint/cancel request
    # 4. DB/event/artifact flush
    # 5. child process join
    # 6. final runtime snapshot
    ...
```

작업 도중 강제 rollback이 더 위험한 경우 현재 atomic operation 완료를 기다리되 timeout을 둔다. timeout 후에는 T-028 recovery marker를 남긴다.

## 19. Configuration Validation

```python
class WatchConfig(BaseModel):
    enabled: bool = True
    input_path: Path
    recursive: bool = False
    stability_interval_seconds: float = 2.0
    required_stable_samples: int = 3
    stability_timeout_seconds: float = 300.0
```

권장 범위:

```text
0.5 <= interval <= 30
2 <= stable samples <= 10
10 <= timeout <= 3600
```

입력 경로가 없거나 읽을 수 없으면 `DEGRADED` 또는 설정 오류로 보고하고 프로세스 자체는 트레이에서 진단 가능하게 유지한다.

## 20. Notification Policy

사용자 알림은 억제 정책을 둔다.

```text
- 정상 개별 사진마다 toast 금지
- batch 완료 요약은 선택 설정
- 첫 오류 또는 상태 전환만 알림
- 같은 오류 반복은 cooldown 적용
- crash loop, watch path missing, DB unavailable는 중요 알림
```

## 21. 테스트 구조

```text
tests/t030/
  test_event_coalescer.py
  test_file_stability.py
  test_exclusion_policy.py
  test_file_identity_dedup.py
  test_runtime_state_reducer.py
  test_pause_resume.py
  test_single_instance.py
  test_worker_supervisor.py
  test_tray_command_idempotency.py
  test_shutdown_recovery.py
```

Windows integration tests:

```text
- named mutex
- named pipe ACL/timeout
- HKCU autostart abstraction
- tray creation/destruction
- shell survives Worker crash
- no orphan worker after exit
```

CI에서 실제 tray UI를 띄울 수 없는 환경은 platform adapter fake를 사용하되, 제품 완료에는 실제 Windows live evidence가 필요하다.

## 22. Artifact와 Evidence

각 핵심 경계에서 JSON evidence를 남긴다.

```text
watch_event.json
stability_result.json
task_registration_result.json
runtime_snapshot.json
tray_command_result.json
worker_supervision_event.json
shutdown_result.json
```

민감한 사용자 전체 경로를 외부 전송하지 않는다. 로컬 로그에서도 필요 시 사용자 home prefix를 축약한다.

## 23. 하네스 명령

```text
python harness/scripts/verify_t030_windows_background_tray.py --project-root .
python harness/scripts/run_t030_background_tray_reference.py --project-root . --output-dir runtime/harness/t030
python harness/scripts/verify_t030_windows_background_tray.py --project-root . --runtime-evidence runtime/harness/t030/t030_runtime_evidence.json
```

실제 구현 완료 검증:

```text
python harness/scripts/verify_t030_windows_background_tray.py \
  --project-root . \
  --runtime-evidence <implementation-runtime-evidence.json> \
  --live-evidence <windows-live-evidence.json> \
  --strict
```

Reference harness evidence는 계약 검증용이며 실제 Windows 완료 증거를 대신하지 않는다.

## 24. 완료 기준

```text
- static contract PASS
- unit/integration tests PASS
- T-019~T-029 regressions PASS
- actual implementation runtime evidence PASS
- Windows live checklist PASS
- approved tray icon source and ICO PASS
- no duplicate task under event storm
- no processing before stable
- no orphan processes after exit
```
