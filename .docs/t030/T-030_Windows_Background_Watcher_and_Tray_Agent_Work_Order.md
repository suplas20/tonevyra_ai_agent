# T-030 — Windows Background Watcher and System Tray Agent 작업 지시서

## 1. 문서 상태

```text
Ticket: T-030
Title: Windows Background Watcher and System Tray Agent
Baseline: T-029 문서·하네스·스킬 패키지
Primary platform: Windows 10/11 x64
Depends on: T-003 watcher/stabilizer, T-009 worker pipeline, T-010 recovery, T-019/T-020 Lightroom bridge, T-028 production reliability
Primary goal: 사용자가 별도 명령을 실행하지 않아도 로그인 세션에서 Tonevyra 에이전트가 백그라운드로 실행되고, 지정 폴더에 새 사진이 안정적으로 들어오면 자동으로 기존 보정 파이프라인을 시작하며, Windows 알림 영역에 Tonevyra 로고 기반 상태 아이콘을 표시한다.
```

## 2. 한 문장 목표

> Windows 사용자 세션에서 단일 Tonevyra 백그라운드 에이전트를 유지하고, 안전한 파일 안정화·중복 방지·영속 큐·복구 절차를 거쳐 새 사진을 자동 처리하며, 시스템 트레이에서 상태 확인과 제한된 운영 명령만 제공한다.

## 3. 용어 정리

사용자가 말한 “작업표시줄 아이콘”은 T-030에서 다음 Windows UI로 구현한다.

```text
Windows notification area / system tray icon
```

메인 창이 없는 백그라운드 앱은 일반 작업표시줄 버튼을 계속 점유하지 않는다. 트레이 아이콘은 Tonevyra 심벌을 사용하며 텍스트 로고는 사용하지 않는다.

## 4. 범위

### 4.1 필수 구현

```text
- Windows 사용자 세션용 Background Agent
- Windows system tray shell
- 사용자별 단일 인스턴스 보장
- 지정 입력 폴더 지속 감시
- Created / Renamed / Moved / Modified 이벤트 coalescing
- 파일 안정화 확인 후에만 작업 등록
- 기존 PostgreSQL image_tasks/task_events 기반 영속 큐 사용
- 중복 작업 방지
- 감시 일시정지 / 재개
- 새 파일 재검색
- 작업 상태와 에이전트 상태를 트레이에 표시
- Worker 크래시 감지 및 제한된 재시작
- Windows 종료·로그아웃·앱 종료 시 graceful shutdown
- 재시작 후 미완료 작업 복구
- Windows 로그인 시 자동 시작을 켜고 끌 수 있는 설정 경로
- 실제 로고 원본에서 생성한 다중 해상도 ICO 자산 계약
```

### 4.2 이번 티켓에서 제외

```text
- 설치 프로그램 제작
- 코드 서명과 배포 패키징
- 전체 React 대시보드 신규 개발
- Windows Service
- 다중 GPU worker pool
- 네트워크 공유 폴더의 무제한 지원
- 입력 원본 자동 삭제 또는 덮어쓰기
- Lightroom UI 좌표 자동화
- AutoHotkey / pyautogui
- 새로운 모델 학습
- SQLite 큐 또는 SQLite fallback
```

설치 프로그램과 코드 보호는 후속 패키징 티켓에서 처리한다. T-030은 실행 구조와 운영 계약을 만든다.

## 5. 핵심 아키텍처

```text
Windows logon
→ Tonevyra Tray Shell 시작
→ 사용자별 named mutex 획득
→ Background Agent Worker 상태 확인/시작
→ 입력 폴더 Watcher 활성화
→ 파일 이벤트 수집 및 debounce
→ File Stability Gate
→ PostgreSQL 작업 등록 또는 기존 작업 재사용
→ 기존 Agent processing loop 실행
→ 분석 → Planner → Lightroom 적용 → Export → Quality
→ Tray 상태/알림 갱신
```

권장 프로세스 경계:

```text
Tonevyra Tray Shell
- 트레이 아이콘
- 메뉴와 알림
- Agent 상태 표시
- Worker lifecycle supervision
- 기존 대시보드 또는 상태 화면 실행

Tonevyra Background Agent Worker
- 폴더 감시
- 파일 안정화
- PostgreSQL 작업 등록
- 작업 큐와 복구
- 모델 분석과 Lightroom pipeline
```

Tray Shell과 Worker는 논리적으로 분리한다. 제품 빌드에서 동일 바이너리의 서로 다른 실행 모드로 묶을 수 있으나, UI 스레드가 모델 추론이나 Lightroom 작업을 직접 수행해서는 안 된다.

## 6. Windows Service 금지

T-030은 Windows Service로 구현하지 않는다.

이유:

```text
- 트레이 UI는 로그인한 사용자 세션에 있어야 한다.
- Lightroom Classic과 동일 사용자 컨텍스트가 필요하다.
- 사용자별 AppData, 입력 폴더, 설정, 라이선스를 사용한다.
- 서비스 세션에서 UI를 표시하는 방식은 지원하지 않는다.
```

기본 실행은 현재 사용자 권한이며 관리자 권한을 요구하지 않는다.

## 7. Agent Runtime State

에이전트 상태는 사진 작업 상태와 분리한다.

허용되는 T-030 runtime state:

```text
STARTING
WATCHING
PROCESSING
PAUSED
DEGRADED
ERROR
STOPPING
STOPPED
```

이 값은 `image_tasks.status`에 기록하지 않는다. 별도 runtime snapshot과 task event evidence에 사용한다.

상태 의미:

```text
STARTING   구성·DB·폴더·Worker 초기화 중
WATCHING   정상 감시 중, 처리 중 작업 없음
PROCESSING 하나 이상의 사진 pipeline 진행 중
PAUSED     사용자가 신규 감시 접수를 일시정지함
DEGRADED   DB, Lightroom, 모델 등 일부 의존성 불가; 프로세스는 살아 있음
ERROR      운영 불가능한 오류로 자동 처리가 정지됨
STOPPING   신규 접수 중단 후 안전 종료 중
STOPPED    프로세스 종료됨
```

기존 사진 작업 상태 enum은 변경하지 않는다.

## 8. System Tray 계약

### 8.1 아이콘

트레이 아이콘은 승인된 Tonevyra 앱 심벌을 사용한다.

```text
- 텍스트 없는 조리개 심벌 + 별
- 투명 배경
- 16, 20, 24, 32, 40, 48, 64, 128, 256 px 포함 ICO
- 밝은/어두운 Windows 배경에서 식별 가능
- 원본 SVG 또는 투명 고해상도 PNG에서 생성
- 사용자가 제공한 화면 캡처를 생산용 원본으로 사용하지 않음
```

승인된 원본 심벌 파일이 저장소에 없으면 기능 개발은 가능하지만 생산 완료는 다음으로 차단한다.

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
```

### 8.2 상태 표현

기본 로고는 유지하고 우측 하단 작은 badge로 상태를 표시한다.

```text
WATCHING / idle: 기본 Aurora Teal
PROCESSING: 기본 로고 + processing badge
PAUSED: warning badge
DEGRADED: warning or offline badge
ERROR: error badge
```

초당 고속 애니메이션은 금지한다. 필요하면 4~8 프레임 이하의 느린 처리 애니메이션 또는 정적 badge를 사용한다.

### 8.3 메뉴

필수 메뉴:

```text
Tonevyra AI
상태 요약
처리 중 / 대기 / 실패 수
대시보드 또는 상태 화면 열기
입력 폴더 열기
완료 폴더 열기
감시 일시정지 / 재개
새 파일 다시 검색
실패 작업 보기
설정
진단 로그 열기
Tonevyra 종료
```

Tray UI는 명령을 Worker에 전달할 뿐 비즈니스 로직을 소유하지 않는다.

## 9. Folder Watcher 계약

### 9.1 파일 이벤트

다음을 감지한다.

```text
Created
Renamed
Moved into watched tree
Modified
```

동일 파일에서 여러 이벤트가 발생하는 것을 정상으로 가정한다. 이벤트는 파일 경로별 debounce/coalescing 후 안정화 검사로 넘긴다.

### 9.2 파일 안정화

새 파일 이벤트 즉시 처리하지 않는다.

기본 정책:

```text
poll interval: 2 seconds
required stable samples: 3
minimum stable duration: 6 seconds
maximum stabilization wait: 300 seconds
```

안정 조건:

```text
- 크기 동일
- 최종 수정 시각 동일
- 읽기 가능
- 0 byte 아님
- 지원 확장자
- 임시/부분 파일 아님
```

설정값은 bounded range 안에서만 변경 가능하다.

### 9.3 지원 확장자

초기 필수:

```text
.cr3 .cr2 .nef .arw .dng .jpg .jpeg
```

기존 코드가 검증된 경우 다음을 추가할 수 있다.

```text
.raf .rw2 .orf .tif .tiff .png
```

추가 확장자는 decoder와 Lightroom 실제 테스트를 통과해야 한다.

### 9.4 제외

```text
hidden files
.tmp .part .crdownload
.xmp .lrcat .lrprev
0 byte files
._* .DS_Store
Tonevyra temp files
완료/실패/캐시/내부 runtime 폴더
```

입력 폴더가 출력 폴더를 포함하거나 반대인 경우 설정을 거부하거나 명시적 exclusion을 요구한다.

## 10. 중복 방지와 영속 큐

SQLite를 추가하지 않는다. 기존 PostgreSQL을 사용한다.

중복 판정 계층:

```text
1. Event coalescer: 동일 경로의 짧은 이벤트 폭주 억제
2. Candidate identity: normalized path + size + mtime_ns
3. Content identity: source_hash 또는 검증된 fast fingerprint
4. DB unique constraint / repository idempotency
```

동일 파일이 다시 감지되면 새 작업을 무조건 만들지 않는다. 기존 작업의 최종 상태와 파일 identity를 확인한다.

정책:

```text
- 동일 identity + 진행/완료 작업 존재: 중복 등록 금지
- 같은 경로지만 내용이 변경됨: 새 identity로 정책에 따라 새 작업 가능
- FAILED 재실행: 명시적 retry command와 새 attempt evidence 필요
```

## 11. 자동 처리 시작

파일이 안정화되고 작업 등록이 완료되면 별도의 사용자 클릭 없이 기존 processing loop를 시작한다.

```text
DETECTED
→ STABILIZING
→ QUEUED
→ ANALYZING
→ ... 기존 파이프라인
```

Lightroom이 연결되지 않은 경우:

```text
- 분석과 Planner까지 안전한 범위에서 진행 가능
- Lightroom 단계에서 무한 spin 금지
- bounded retry/backoff와 DEGRADED 상태 사용
- task status를 임의 새 값으로 만들지 않음
- 기존 task event와 incident evidence 기록
```

## 12. 동시성

기존 MVP 동시성 원칙을 유지한다.

```text
- 모델/GPU main processing concurrency: 1
- Lightroom apply/export: 항상 1
- 파일 안정화 검사와 경량 metadata probe만 제한된 병렬 가능
```

여러 파일은 FIFO를 기본으로 하되 기존 우선순위 정책이 있으면 그대로 사용한다.

## 13. Pause / Resume

`PAUSED`는 신규 파일을 pipeline에 넣는 행위만 중단한다.

```text
- 이미 진행 중인 atomic stage는 안전하게 완료 또는 checkpoint 후 중단
- 파일 이벤트는 버리거나 무한 메모리 축적하지 않음
- resume 시 bounded rescan으로 누락 파일 확인
- pause 상태도 프로세스 재시작 후 설정에서 복원
```

## 14. Single Instance

사용자별 단일 Tray Shell과 단일 Worker만 허용한다.

권장:

```text
Local\TonevyraAI.Tray.<UserSID>
Local\TonevyraAI.Agent.<UserSID>
```

두 번째 실행:

```text
- 새 Worker를 시작하지 않음
- 기존 Tray에 activate/open 요청
- 즉시 종료
```

단일 인스턴스 검증을 파일 lock 하나에만 의존하지 않는다. Windows named mutex 또는 동등한 커널 primitive를 사용한다.

## 15. Shell–Worker IPC

우선순위:

```text
1. Windows named pipe 또는 multiprocessing AF_PIPE
2. 기존 프로젝트의 인증된 local IPC abstraction
```

금지:

```text
- 외부 인터페이스에 0.0.0.0 listener 노출
- 인증 없는 로컬 HTTP command endpoint
- Tray가 DB를 직접 수정해 Worker 명령을 흉내냄
```

필수 command:

```text
GET_STATUS
PAUSE_WATCHING
RESUME_WATCHING
RESCAN
OPEN_INPUT_FOLDER
OPEN_OUTPUT_FOLDER
RETRY_FAILED_JOB
SHUTDOWN
```

모든 상태 변경 command는 idempotent하고 audit evidence를 남긴다.

## 16. Worker Supervision

Tray Shell은 Worker heartbeat를 확인한다.

```text
- heartbeat timeout은 설정된 bounded 값
- 자동 재시작 횟수 제한
- crash loop 감지
- 제한 초과 시 ERROR 상태와 사용자 알림
- 기존 T-028 incident/checkpoint/recovery 증거 재사용
```

무한 자동 재시작은 금지한다.

## 17. 종료와 Windows 세션 이벤트

종료 순서:

```text
1. STOPPING
2. 신규 watcher intake 차단
3. 현재 stage의 안전 checkpoint 요청
4. queue/agent 상태 evidence flush
5. watcher와 IPC 종료
6. Worker 종료 확인
7. Tray icon 제거
```

Windows 종료·로그아웃·앱 종료에서 동일한 경계를 사용한다. 강제 종료 후 다음 실행에서 T-028 recovery가 미완료 작업을 재조정해야 한다.

## 18. 설정

필수 설정:

```text
watch_enabled
watch_input_path
watch_recursive
watch_stability_interval_seconds
watch_required_stable_samples
watch_stability_timeout_seconds
autostart_enabled
tray_enabled
worker_restart_limit
worker_heartbeat_timeout_seconds
```

경로 설정은 canonicalized path로 저장하고 입력/출력/내부 폴더 겹침을 검증한다.

## 19. 권장 모듈

```text
src/tonevyra_agent/windows/
  tray_shell.py
  tray_menu.py
  tray_state.py
  tray_icons.py
  single_instance.py
  startup_registration.py
  session_events.py
  shell_worker_ipc.py
  worker_supervisor.py

src/tonevyra_agent/watcher/
  folder_watcher.py
  event_coalescer.py
  file_stability.py
  file_identity.py
  exclusion_policy.py
  rescan.py

src/tonevyra_agent/agent/
  background_runtime.py
  runtime_state.py
  lifecycle.py
```

같은 책임의 기존 모듈이 있으면 새로 중복 생성하지 않고 확장한다.

## 20. 오류 코드

코드 enum과 테스트를 함께 갱신해 다음을 명시적으로 지원한다.

```text
WATCH_PATH_NOT_CONFIGURED
WATCH_PATH_NOT_FOUND
WATCH_PATH_NOT_READABLE
WATCH_OUTPUT_RECURSION_RISK
FILE_STABILIZATION_TIMEOUT
FILE_IDENTITY_FAILED
DUPLICATE_FILE_IGNORED
AGENT_INSTANCE_ALREADY_RUNNING
WORKER_HEARTBEAT_TIMEOUT
WORKER_CRASH_LOOP
TRAY_ICON_ASSET_MISSING
TRAY_IPC_UNAVAILABLE
AUTOSTART_REGISTRATION_FAILED
GRACEFUL_SHUTDOWN_TIMEOUT
```

오류 코드를 추가할 때 기존 프로젝트 enum·DB·문서·테스트 정책을 따른다.

## 21. 하드 게이트

```text
GATE-01  로그인 사용자 세션에서 Tray가 한 번만 실행된다.
GATE-02  Tray icon은 승인된 Tonevyra 심벌을 사용한다.
GATE-03  새 사진은 안정화 후 정확히 한 번만 작업 등록된다.
GATE-04  복사 중인 RAW는 처리하지 않는다.
GATE-05  입력/출력 재귀 루프가 없다.
GATE-06  원본은 덮어쓰거나 삭제하지 않는다.
GATE-07  pause/resume/rescan이 idempotent하다.
GATE-08  Worker crash 후 Tray는 유지되고 bounded recovery를 수행한다.
GATE-09  두 번째 인스턴스가 작업을 중복 처리하지 않는다.
GATE-10  재시작 후 큐와 미완료 작업이 복구된다.
GATE-11  Windows 종료 시 상태·checkpoint를 안전하게 기록한다.
GATE-12  모델과 Lightroom의 main concurrency는 1이다.
GATE-13  Tray UI가 Planner/품질/DB 비즈니스 로직을 소유하지 않는다.
GATE-14  T-019~T-029 회귀 테스트가 유지된다.
GATE-15  실제 Windows live evidence가 없으면 제품 완료를 선언하지 않는다.
```

## 22. 차단 상태

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
BLOCKED_WINDOWS_SESSION_TEST_UNAVAILABLE
BLOCKED_SINGLE_INSTANCE_PRIMITIVE
BLOCKED_WORKER_RECOVERY_REGRESSION
BLOCKED_WATCH_PATH_PERMISSION
```

차단 상태에서는 우회 구현으로 완료 처리하지 않는다.

## 23. 완료 증거

필수 산출물:

```text
agent_runtime_snapshot.json
watch_event_evidence.json
file_stability_evidence.json
deduplication_evidence.json
single_instance_evidence.json
pause_resume_evidence.json
worker_crash_recovery_evidence.json
shutdown_recovery_evidence.json
tray_state_evidence.json
windows_live_test_evidence.json
```

실제 Windows live test는 최소 다음을 포함한다.

```text
- 트레이 아이콘 화면 증거
- 2GB 이하가 아닌 실제 RAW 또는 큰 테스트 파일의 복사 중 대기 증거
- 복사 완료 후 자동 queue/process 증거
- duplicate event 1회 등록 증거
- pause/resume
- Worker 강제 종료 후 bounded recovery
- 앱 종료 후 orphan process 없음
```

## 24. Stop Rule

T-030 구현과 검증까지만 수행한다. 설치 프로그램, 코드 보호, 모델 암호화, 상용 라이선스, 전체 대시보드 재설계로 확장하지 않는다.
