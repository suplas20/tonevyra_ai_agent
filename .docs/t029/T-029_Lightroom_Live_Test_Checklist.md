# T-029 Lightroom Classic 실제 마스킹 테스트 체크리스트

## 0. 2026-06-29 Scope Update — Native Mask Only

방사형 그레이디언트 / `radial_template` fallback은 T-029 검증 범위에서 제외한다.

이 체크리스트의 radial preset, radial geometry retention, radial template application 항목은 superseded로 취급한다. 실제 완료 증거는 native mask가 의도한 target을 검출하고 자동 적용되는 경우에만 인정한다. Native target detection failure case는 `skip_local` 또는 `review_required` evidence를 요구한다.

## 1. 테스트 정보

```text
Date:
Operator:
OS:
Lightroom Classic version:
Camera Raw version:
Tonevyra plugin version:
Template library version:
Manifest SHA-256:
Source image SHA-256:
```

사용 이미지:

```text
harness/fixtures/images/t029_background_person_red_recovery.jpg
```

## 2. Phase 0 — 단일 radial preset PoC

```text
[ ] 검증된 seed radial preset이 준비됨
[ ] Plugin이 사용자 드래그 없이 preset을 자동 적용함
[ ] mask center가 예상 위치에 유지됨
[ ] width/height가 유지됨
[ ] feather가 유지됨
[ ] result JSON이 생성됨
[ ] 같은 request replay 시 duplicate mask가 생기지 않음
[ ] 기존 사용자 마스크가 유지됨
[ ] 실패 주입 시 rollback 또는 안전한 failure result가 남음
```

필수 evidence:

```text
phase0_request.json
phase0_result.json
develop_before.json
develop_after.json
mask_overlay_screenshot.png
phase0_replay_result.json
```

## 3. Native detection 실패 확인

이 테스트는 Lightroom AI 성능 평가가 아니라 fallback 조건 확인이다.

```text
[ ] foreground diver는 main subject로 인식될 수 있음
[ ] upper-left background person은 target person/object로 인식되지 않음
[ ] native_assessment.target_detected = false
[ ] reason_code = NATIVE_TARGET_NOT_DETECTED
[ ] Planner가 radial_template을 선택함
```

## 4. Target geometry 확인

예상 target는 배경 인물의 붉은 의상 주변이다.

```text
center_x ≈ 0.27
center_y ≈ 0.15
width ≈ 0.15
height ≈ 0.12
```

허용 오차는 실제 Planner policy를 따른다.

```text
[ ] EXIF orientation이 반영됨
[ ] 선택 template center가 upper-left target에 위치함
[ ] 대상 의상이 mask 내부에 충분히 포함됨
[ ] foreground diver의 얼굴/상의는 mask에서 제외되거나 영향이 미미함
[ ] 좌측 주황색 로프와 우측 창 영역에 과도한 영향이 없음
```

## 5. 색상 복원 확인

```text
[ ] 대상 의상의 red/chroma가 보정 전보다 회복됨
[ ] 적색이 형광 또는 과포화로 변하지 않음
[ ] 주변 파란 벽과 물에 붉은 얼룩이 보이지 않음
[ ] 배경 인물 피부/다리에 부자연스러운 마젠타가 생기지 않음
[ ] 밝은 창 영역 clipping이 증가하지 않음
[ ] mask 경계가 보이지 않음
```

## 6. Plugin 결과 확인

```text
[ ] schema_version = t029.mask_apply.result.v1
[ ] status가 실제 적용 결과와 일치함
[ ] template checksum verified = true
[ ] mask_name이 Tonevyra::T029 namespace임
[ ] pre/post snapshot reference 존재
[ ] capability snapshot 존재
[ ] operation result와 applied adjustment가 일치함
[ ] warning/error가 숨겨지지 않음
```

## 7. Idempotency·복구

```text
[ ] 동일 idempotency key 재실행 시 created가 아니라 reused/no-op임
[ ] mask count가 증가하지 않음
[ ] checksum mismatch fixture는 적용 전에 거부됨
[ ] 중간 실패 후 사용자 마스크가 유지됨
[ ] source 원본 파일이 수정되지 않음
[ ] request/result 파일이 atomic하게 남음
```

## 8. Export·Quality evidence

```text
[ ] T-020 export 성공
[ ] 실제 non-empty output file 존재
[ ] target crop before/after evidence 존재
[ ] target_color_recovery_gain 기록
[ ] background_color_spill 기록
[ ] neutral_or_skin_shift 기록
[ ] highlight_clipping_delta 기록
[ ] radial alignment evidence 기록
[ ] 최종 quality decision이 Plugin이 아니라 Agent에서 생성됨
```

## 9. 통과 조건

다음이 모두 만족되어야 한다.

```text
Phase 0 pass
radial fallback selected
mask target aligned
local adjustment bounded
red recovery visible/measurable
spill below policy threshold
no duplicate on replay
user masks preserved
strict T-029 verifier pass
T-019..T-028 regressions pass
```

## 10. 실패 기록

```text
Failure stage:
Error code:
Expected:
Actual:
Request path:
Result path:
Screenshot/evidence path:
Rollback result:
Reproduction steps:
Recommended next action:
```
