# T-030 Windows Live Test Checklist

## 1. 목적

실제 Windows 10/11 사용자 세션에서 Background Agent, system tray, folder watcher, recovery가 계약대로 동작하는지 검증한다. Fake tray 또는 reference harness 결과만으로 완료 처리하지 않는다.

## 2. 테스트 환경 기록

```text
Windows edition/build:
User account type:
Python/build package version:
Tonevyra commit/build ID:
PostgreSQL version:
Lightroom Classic version:
GPU/driver:
Watch path:
Output path:
Recursive watch enabled:
Approved icon asset hash:
Test date/time:
Tester:
```

## 3. 사전 조건

```text
[ ] T-019~T-029 필수 회귀 테스트 통과
[ ] PostgreSQL 연결 정상
[ ] 입력 폴더와 출력 폴더가 겹치지 않음
[ ] Tonevyra approved symbol source 존재
[ ] 다중 해상도 ICO 생성 및 manifest/hash 기록
[ ] 실제 RAW 테스트 파일 준비
[ ] 큰 파일의 느린 복사를 재현할 수 있음
[ ] Process Explorer 또는 Task Manager 사용 가능
```

## 4. Tray 기본 동작

```text
[ ] Tray 실행 후 알림 영역에 Tonevyra 심벌 표시
[ ] 일반 작업표시줄에 불필요한 빈 메인 창이 남지 않음
[ ] tooltip에 현재 상태 표시
[ ] 우클릭 메뉴 항목 정상 표시
[ ] 더블 클릭 또는 열기 동작으로 기존 상태/대시보드 화면 표시
[ ] 밝은 Windows 테마에서 식별 가능
[ ] 어두운 Windows 테마에서 식별 가능
[ ] 100%, 125%, 150%, 200% DPI에서 깨짐 없음
```

증거:

```text
tray_idle_screenshot:
tray_menu_screenshot:
light_theme_screenshot:
dark_theme_screenshot:
dpi_test_notes:
```

## 5. Single Instance

```text
[ ] 첫 Tray/Worker 실행 성공
[ ] 두 번째 Tray 실행 시 새 Worker가 생기지 않음
[ ] 두 번째 실행은 기존 UI activate 후 종료
[ ] Task Manager에서 Tray 1개, Worker 1개 이하
[ ] 사용자 A와 사용자 B의 per-user isolation 정책 확인 가능하면 검증
```

## 6. 새 파일 감지

```text
[ ] JPG 직접 복사 감지
[ ] RAW 직접 복사 감지
[ ] 임시 파일명으로 복사 후 rename 감지
[ ] 다른 폴더에서 move-in 감지
[ ] recursive=false에서 하위 폴더 파일 무시
[ ] recursive=true에서 하위 폴더 파일 감지
```

## 7. 복사 중 파일 안정화

느린 복사 또는 throttled copy를 사용한다.

```text
[ ] Created 이벤트 후 즉시 ANALYZING으로 가지 않음
[ ] 파일 크기가 변하는 동안 WAIT_STABLE evidence 지속
[ ] 마지막 변경 후 required stable samples 충족
[ ] 안정화 이후에만 image_tasks 등록/처리 시작
[ ] stabilization timeout은 실패 evidence를 남기고 무한 대기하지 않음
```

필수 시간 증거:

```text
first_seen_at:
last_size_change_at:
stable_at:
task_registered_at:
analysis_started_at:
```

관계:

```text
analysis_started_at >= stable_at
```

## 8. Event Storm / 중복 방지

```text
[ ] 하나의 사진에 Created + 여러 Modified + Renamed 발생
[ ] coalesced event count가 1보다 큼
[ ] image_tasks 신규 row는 1개
[ ] pipeline external execution은 1회
[ ] 에이전트 재시작 후 동일 파일 rescan도 중복 처리하지 않음
```

## 9. Exclusion과 재귀 방지

```text
[ ] .tmp, .part, .crdownload 무시
[ ] .xmp, .lrcat 무시
[ ] 0 byte 파일 처리하지 않음
[ ] Tonevyra output 파일을 입력으로 다시 처리하지 않음
[ ] 입력 폴더 안에 output을 설정하려 하면 거부 또는 명시 exclusion
[ ] junction/symlink loop가 가능하면 안전하게 중단
```

## 10. Pause / Resume / Rescan

```text
[ ] Pause 후 runtime state=PAUSED
[ ] Pause 중 신규 파일이 자동 처리되지 않음
[ ] 진행 중 atomic stage는 손상 없이 완료/checkpoint
[ ] Resume 후 신규 접수 재개
[ ] Resume bounded rescan이 pause 중 파일을 발견
[ ] pause/resume command 재실행이 NO_OP 또는 idempotent APPLIED
[ ] rescan 반복이 중복 task를 만들지 않음
```

## 11. Lightroom/Model dependency outage

```text
[ ] Lightroom 미실행 상태에서 Agent 프로세스 유지
[ ] runtime state가 DEGRADED로 표시
[ ] 무한 빠른 retry 없음
[ ] Lightroom 실행/Plugin 연결 후 정상 복구
[ ] 모델 로드 실패 시 Agent 전체 즉시 crash 대신 명시 오류
[ ] dependency 복구 후 pending 작업 정책 확인
```

## 12. Worker Crash Recovery

```text
[ ] Worker process 강제 종료
[ ] Tray icon은 유지
[ ] heartbeat timeout 감지
[ ] bounded restart 수행
[ ] restart 후 기존 큐/recovery 실행
[ ] 같은 Lightroom apply/export 외부 효과가 중복되지 않음
[ ] restart limit 초과 시 ERROR와 crash-loop 알림
```

## 13. Windows 종료/로그아웃/앱 종료

```text
[ ] Tray의 Tonevyra 종료 선택
[ ] 신규 intake 중단
[ ] Worker 안전 종료
[ ] Tray icon 제거
[ ] orphan process 없음
[ ] 재실행 시 미완료 작업 복구
[ ] Windows 로그아웃 이벤트 테스트 가능하면 수행
[ ] Windows 재부팅 후 autostart 설정에 따라 실행 여부 확인
```

## 14. Autostart

```text
[ ] startup enable은 current user 범위만 변경
[ ] 관리자 권한 불필요
[ ] startup status 정확
[ ] startup disable 후 재로그인에서 실행 안 됨
[ ] 개발 Python 임시 경로가 release 등록에 남지 않음
```

## 15. 원본 안전성

테스트 전후 hash를 비교한다.

```text
[ ] 원본 파일 SHA-256 동일
[ ] 원본 mtime을 의도치 않게 변경하지 않음
[ ] 원본 이동/삭제 없음
[ ] 실패 시에도 원본 유지
```

## 16. 성능/Soak

```text
[ ] 100장 이상 순차 투입
[ ] watcher event loss 없음 또는 overflow 후 rescan 복구
[ ] 메모리 지속 증가 없음
[ ] Tray 반응성 유지
[ ] Worker main concurrency=1
[ ] CPU idle 사용량 합리적
[ ] 8시간 이상 감시 soak에서 crash 없음
```

## 17. 완료 판정

PASS 조건:

```text
- 모든 필수 항목 PASS
- 생산용 승인 아이콘 자산 존재
- 중복 외부 효과 0
- 복사 중 처리 0
- 원본 변경 0
- orphan process 0
- T-019~T-029 regression PASS
```

차단 코드:

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
BLOCKED_WINDOWS_SESSION_TEST_UNAVAILABLE
BLOCKED_SINGLE_INSTANCE_PRIMITIVE
BLOCKED_WORKER_RECOVERY_REGRESSION
BLOCKED_WATCH_PATH_PERMISSION
```

## 18. Live Evidence JSON

최종 증거는 `harness/schemas/t030_runtime_evidence.schema.json`과 별도 Windows live evidence 계약을 만족해야 한다.

```json
{
  "schema_version": "t030.windows_live_evidence.v1",
  "ticket": "T030",
  "platform": "Windows",
  "windows_build": "...",
  "implementation_build": "...",
  "tray_icon_asset_approved": true,
  "tray_visible": true,
  "single_instance_passed": true,
  "copy_in_progress_blocked": true,
  "deduplication_passed": true,
  "pause_resume_passed": true,
  "worker_crash_recovery_passed": true,
  "no_duplicate_external_effects": true,
  "graceful_shutdown_passed": true,
  "no_orphan_processes": true,
  "source_integrity_passed": true,
  "regressions_passed": true,
  "screenshots": [],
  "evidence_paths": [],
  "completed": true
}
```
