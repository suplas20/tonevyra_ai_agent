# T-019 Folder-Driven Lightroom Live Test Checklist

이 체크리스트는 실제 PC에 설치된 Lightroom Classic에서 Tonevyra plugin을 검증하기 위한 절차이다.

중요: 이 테스트는 Lightroom에서 사진을 선택하고 메뉴를 누르는 테스트가 아니다. 사용자는 지정 입력 폴더에 사진을 넣고, agent와 plugin이 자동으로 처리하는지 확인한다.

## 사전 조건

- Lightroom Classic 설치 완료
- Tonevyra Python runtime 설정 완료
- `TONEVYRA_INPUT_DIR` 또는 프로젝트 입력 폴더 확인
- `TONEVYRA_RUNTIME_DIR` 확인
- 테스트용 사진 1장 준비
- 기존 하네스 통과 상태 확인

## 설치/로드 테스트

1. Lightroom Classic 실행
2. Plug-in Manager 열기
3. `TonevyraAI.lrplugin` 추가
4. 플러그인 상태 확인
   - 기대값: Installed and running
5. Tonevyra bridge worker 상태 확인
   - 기대값: worker running 또는 diagnostics에서 정상 표시

## 자동 실행 테스트

1. Lightroom에서 사진을 선택하지 않는다.
2. Tonevyra agent를 실행한다.
3. 테스트 사진 1장을 지정 입력 폴더에 복사한다.
4. folder watcher가 task를 생성했는지 확인한다.
5. correction plan 생성 여부를 확인한다.
6. apply request JSON 생성 확인
   - 위치: `runtime/bridge/lightroom_apply_requests/<request_id>.json`
7. Lightroom plugin worker가 request를 처리했는지 확인한다.
8. apply result JSON 생성 확인
   - 위치: `runtime/bridge/lightroom_apply_results/<request_id>.json`
9. Lightroom catalog에서 해당 source_path 사진에 보정값이 적용되었는지 확인한다.
10. DB evidence 또는 `task_events.payload_json` 연결을 확인한다.

## 실패 테스트

다음 실패 시나리오 중 가능한 항목을 최소 2개 검증한다.

- Lightroom plugin 미실행 상태에서 apply request 발생
- source path missing
- invalid apply request schema
- unsupported develop parameter 포함
- apply result timeout
- catalog import 실패

각 실패는 자동 처리 실패로 evidence JSON에 남아야 한다.

## evidence 제출

작업자는 다음 파일을 작업 보고서에 첨부하거나 경로를 남긴다.

- folder watcher task evidence
- correction plan evidence
- apply request JSON
- apply result JSON
- Lightroom plugin load 상태 스크린샷 또는 수동 확인 로그
- 실패 시나리오 evidence

## 완료 기준

- plugin loaded
- worker running
- input folder file detected
- task created
- apply request written
- apply result written
- at least one develop setting applied
- existing harness still passes
- no selected-photo-based product flow
