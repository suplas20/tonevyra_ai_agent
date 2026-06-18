# Document Deduplication and T-019 Validation Report

Generated: 2026-06-18
Project root 기준: `F:\tonevyra_ai_agent`

## 1. 처리 요약

업로드된 `.docs.zip`에는 Markdown 문서 41개가 포함되어 있었다. 이 중 루트의 `_Qwen3Commercial_Agent.md` 계열 16개는 현재 canonical 문서와 같은 번호/주제를 가진 과거 정책 분기 문서로 확인되어 삭제 대상으로 분류했다.

추가로 `t019/T-019_LIGHTROOM_FOLDER_DRIVEN_PACKAGE_README.md`는 프로젝트 내부 기준 문서가 아니라 ZIP 전달/병합용 README였기 때문에 `.docs` 정리본에서는 제거했다.

정리 후 문서 수: 24개
삭제/제거 대상: 17개

## 2. 삭제한 문서

| 문서 | 처리 | 이유 |
|---|---|---|
| `00_Loop_Engineering_Global_Addendum_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `01_PRD_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `02_System_Architecture_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `03_Data_Persistence_Architecture_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `04_PostgreSQL_Database_Schema_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `05_Artifact_Storage_Specification_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `06_Lightroom_Plugin_Bridge_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `07_Agent_Core_State_Machine_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `08_Vision_Analysis_Design_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `09_Correction_Planner_Design_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `10_Quality_Gate_Design_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `11_Folder_Watcher_File_Pipeline_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `12_CLI_Operations_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `13_Crash_Recovery_Error_Handling_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `14_Testing_QA_Strategy_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `15_Development_Roadmap_Milestones_Agent_Qwen3Commercial_Agent.md` | DELETE | Stale duplicate of canonical 00-15 design doc; model policy now consolidated in canonical docs/reports. |
| `t019/T-019_LIGHTROOM_FOLDER_DRIVEN_PACKAGE_README.md` | DELETE | Package-transfer README; not an implementation source of truth inside project .docs. |

## 3. 유지한 핵심 문서

- `00_Loop_Engineering_Global_Addendum_Agent.md` ~ `15_Development_Roadmap_Milestones_Agent.md`: 현재 canonical agent 설계 문서
- `implementation/Tonevyra_AI_Implementation_Readiness_Agent_v2.md`: 구현 준비 기준 문서
- `implementation/Tonevyra_AI_Implementation_Work_Order_Agent_v2.md`: 전체 구현 작업 지시서
- `reports/harness_skill_alignment_report.md`: 하네스/스킬 정렬 결과
- `reports/task_update_impact_report.md`: 기존 작업 업데이트 영향 분석
- `t019/T-019_Lightroom_Plugin_Implementation_Work_Order.md`: T-019 실구현 기준 문서
- `t019/T-019_Codex_Prompt.md`: Codex 실행 프롬프트
- `t019/Lightroom_Plugin_Bridge_Contract.md`: T-019 bridge schema 계약
- `t019/Lightroom_Plugin_Live_Test_Checklist.md`: 실제 Lightroom Classic 테스트 체크리스트

## 4. T-019 검증 결과

| 항목 | 결과 | 설명 |
|---|---|---|
| Folder-driven 기본 UX | PASS | T-019 문서는 사용자가 Lightroom에서 사진을 선택하는 구조가 아니라 input folder 감지 기반 자동 보정을 기준으로 한다. |
| Lightroom plugin 역할 | PASS | plugin은 AI 실행부가 아니라 apply request를 처리하는 thin worker/bridge로 제한되어 있다. |
| Agent → plugin → agent 방향성 | PASS | apply request/result 계약이 Python agent 기준으로 정의되어 있다. |
| `source_path` 기준 | PASS | Lightroom catalog photo 식별보다 folder watcher의 `source_path`를 우선한다. |
| Evidence 기록 | PASS | `task_events.payload_json`, apply request/result, error evidence 기록 요구가 포함되어 있다. |
| 선택 사진 기반 회귀 방지 | PASS | `getTargetPhoto`, `RUN_TONEVYRA_CORRECTION`, `selected_photo_detected`, `selected_count` 같은 직접 회귀 토큰은 T-019 기준 문서에 없다. |
| 프로젝트 경로 반영 | PASS | T-019 문서에 `F:\tonevyra_ai_agent` 기준 경로를 추가했다. |

### 4.1 필수 개념 토큰 확인

다음 필수 개념이 T-019 문서에 존재한다: `folder watcher`, `input folder`, `Lightroom apply request`, `Lightroom apply result`, `source_path`, `task_events.payload_json`, `non_destructive`, `APPLY_LIGHTROOM_SETTINGS`.

### 4.2 hard-forbidden 회귀 토큰 확인

T-019 기준 문서에서 `getTargetPhoto`, `RUN_TONEVYRA_CORRECTION`, `selected_photo_detected`, `selected_count`는 발견되지 않았다.



## 4.3 추가 정렬 사항

검토 중 `implementation/Tonevyra_AI_Implementation_Work_Order_Agent_v2.md`의 과거 T-016 Real Lightroom Lua PoC 섹션이 `src/tonevyra_agent/lightroom/plugin/TonevyraAI.lrplugin` 경로를 언급하는 것을 확인했다. 이는 과거 PoC 기준으로 남아 있으면 T-019 실구현 경로와 혼동될 수 있으므로, T-016을 "historical bridge PoC context"로 표시하고 실제 구현 기준은 T-019 및 `F:	onevyra_ai_agent\lightroom\TonevyraAI.lrplugin`로 정규화했다.

`06_Lightroom_Plugin_Bridge_Agent.md`에도 T-019 folder-driven update 섹션을 추가해, selected-photo/menu-first 흐름으로 회귀하지 않도록 명시했다.

## 5. 경로 정규화

다음 기준을 T-019 문서에 반영했다.

```text
프로젝트 루트: F:\tonevyra_ai_agent
Lightroom plugin: F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin
문서 위치: F:\tonevyra_ai_agent\.docs
Bridge root: F:\tonevyra_ai_agent\runtime\bridge
Input folder 기본값: F:\tonevyra_ai_agent\runtime\input
```

## 6. 적용 방법

정리본 ZIP을 사용할 경우, 현재 프로젝트의 `.docs` 폴더를 바로 덮어쓰기보다는 Git diff를 확인한 뒤 반영한다.

```powershell
cd F:\tonevyra_ai_agent
git status
# 필요하면 현재 .docs 백업
Copy-Item .\.docs .\.docs_backup_before_cleanup -Recurse
# 정리본 압축 해제 후 비교 병합
```

삭제 대상만 수동 제거하려면 함께 제공되는 `apply_docs_cleanup.ps1`을 참고한다.

## 7. 결론

- `_Qwen3Commercial_Agent.md` 계열은 중복/과거 분기 문서이므로 제거하는 것이 맞다.
- T-019의 현재 문서 방향은 folder-driven 설계와 일치한다.
- T-019 문서에서 사용자가 Lightroom에서 사진을 선택해 실행하는 흐름은 기본 UX가 아니라 금지/디버그 문맥으로만 언급된다.
- 프로젝트 경로 기준은 `F:\tonevyra_ai_agent`로 정규화했다.
