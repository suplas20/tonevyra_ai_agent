# T-029 문서·하네스·스킬 업데이트 보고서

## 2026-06-29 Scope Update

방사형 그레이디언트 / `radial_template` fallback은 T-029 범위에서 제외되었다.

이 업데이트 이후 T-029의 계약과 하네스는 native Lightroom mask execution only를 기준으로 한다. Native target detection이 실패한 경우 기대 결과는 `review_required` 또는 `skip_local`이며, radial template 선택이나 radial preset 적용은 완료 증거가 아니다.

## 1. 목적

현재 Tonevyra AI Lightroom Classic 플러그인에 로컬 마스킹 실행 기능을 추가하기 위한 T-029 작업 패키지를 구성했다. 핵심 사례는 Subject, People, Object가 인식하지 못하는 작은 배경 인물의 붉은 의상을 자동으로 복원하는 것이다.

## 2. 결정된 구현 방향

```text
Qwen/Analysis: target 의미, normalized geometry, 색 손실 evidence
Mask Strategy Planner: native 신뢰성 확인, radial template 선택, fit/clamp
Lightroom Plugin: 검증된 request와 template ID만 실행
Quality Gate: target recovery와 background spill 평가
```

MVP 방사형 마스크는 임의 런타임 XMP 생성이 아니라, 지원 Lightroom 버전에서 검증한 seed preset 기반의 버전형 template library를 사용한다.

## 3. 신규 작업 문서

```text
.docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md
.docs/t029/T-029_Implementation_Specification.md
.docs/t029/T-029_Codex_Prompt.md
.docs/t029/T-029_Lightroom_Live_Test_Checklist.md
.docs/t029/T-029_Seed_Radial_Preset_Preparation_Guide.md
```

## 4. 신규 스킬

```text
skills/lightroom-radial-mask-execution/SKILL.md
skills/radial-mask-template-library/SKILL.md
skills/T029_SKILL_INVENTORY.json
```

스킬 보존 결과:

```text
T-028 baseline: 41
T-029 added: 2
T-029 cumulative: 43
```

기존 스킬은 삭제·병합·이름 변경하지 않았다.

## 5. 신규 하네스

```text
harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md
harness/HARNESS_ENV_T029_LIGHTROOM_RADIAL_MASKING.example
harness/T029_RADIAL_MASKING_UPDATE_MANIFEST.json
harness/prompts/09_t029_lightroom_radial_masking_prompt.md
harness/schemas/t029_mask_apply_request.schema.json
harness/schemas/t029_mask_apply_result.schema.json
harness/schemas/t029_radial_template_manifest.schema.json
harness/scripts/verify_t029_lightroom_radial_masking.py
harness/scripts/run_t029_radial_masking_runtime.py
harness/fixtures/t029_radial_masking/*
harness/fixtures/images/t029_background_person_red_recovery.jpg
```

## 6. 하네스 검증 범위

```text
required document/skill/file presence
41 → 43 skill preservation
JSON Schema draft 2020-12 declarations
normalized geometry bounds
template ID/version/checksum
forbidden Provider execution fields
bounded local adjustments
native target detection failure → radial fallback
deterministic template selection
idempotent replay
rollback and user-mask preservation
runtime evidence
strict real-Lightroom evidence
```

Deterministic runtime harness는 실제 Lightroom 마스크 생성을 모사하지 않는다. 실제 완료는 별도의 `t029.live.evidence.v1`을 요구한다.

## 7. 업데이트한 전역 문서

```text
AGENTS.md
CLAUDE.md
.docs/02_System_Architecture_Agent.md
.docs/06_Lightroom_Plugin_Bridge_Agent.md
.docs/08_Vision_Analysis_Design_Agent.md
.docs/09_Correction_Planner_Design_Agent.md
.docs/10_Quality_Gate_Design_Agent.md
.docs/14_Testing_QA_Strategy_Agent.md
.docs/15_Development_Roadmap_Milestones_Agent.md
.docs/implementation/Tonevyra_AI_Implementation_Readiness_Agent_v2.md
.docs/implementation/Tonevyra_AI_Implementation_Work_Order_Agent_v2.md
harness/CONTRACT.md
harness/HARNESS_ENV.example
harness/README.md
skills/README.md
```

관련 기존 스킬에도 T-029 연계 규칙을 추가했다.

## 8. 기술적 차단 게이트

Codex는 먼저 실제 Lightroom Classic에서 미리 만든 radial preset 1개를 Plugin이 자동 적용하고 geometry가 유지되는지 증명해야 한다.

다음이 실패하면 구현을 우회하지 않고 중단한다.

```text
preset 자동 적용 불가
geometry 유지 불가
user mask 보존 불가
idempotent replay 불가
rollback 또는 안전 실패 증명 불가
```

금지된 우회:

```text
AutoHotkey / pyautogui
화면 좌표 클릭/드래그
Lightroom catalog DB 수정
사용자 sidecar XMP 덮어쓰기
검증되지 않은 private API
```

## 9. 패키지 자체 검증 결과

```text
T-029 static contract and fixtures: PASS
T-029 deterministic planning/template-selection self-test: PASS
Selected strategy: radial_template
Selected template: radial.r01.c01.small.vertical.f80
T-019..T-028 regression result: not asserted by this documentation-package self-test
Real Lightroom strict result: not run; Codex implementation evidence required
Skill inventory: 43
```

실 Lightroom strict gate는 Codex가 실제 Plugin 구현 후 실행해야 한다.
