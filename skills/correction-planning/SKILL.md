---
name: correction-planning
description: Convert validated vision analysis into safe, clamped Lightroom correction parameters with sticky requires_review. Use this skill when implementing correction/planner.py, designing correction rules, mapping issues to Lightroom values, tuning safe ranges, or adding retry correction logic. Always consult before changing any adjustment value handling.
---

# Correction Planning

## 역할

Planner가 Lightroom 보정값의 최종 권한자다. 모델은 분석하고, Planner가 결정한다.
어떤 것도 Planner를 우회하지 않는다.

```text
vision_structured.json → Correction Planner → correction_plan.json → lightroom-bridge
```

## Input / Output

입력: VisionAnalysisResult, EXIF 요약, (재시도 시) 이전 quality result + retry history, config 범위.
출력: `CorrectionPlan` — base_preset, style_target, adjustments, confidence,
**requires_review**, **clamped**, reasoning_summary, optional risk_flags.

```json
{
  "base_preset": "Underwater Standard",
  "style_target": "natural_clean",
  "adjustments": {
    "exposure": 0.45, "contrast": 18, "highlights": -22, "shadows": 38,
    "temperature_delta": 800, "tint": 12, "vibrance": 24, "dehaze": 12
  },
  "confidence": 0.82,
  "requires_review": false,
  "clamped": false,
  "reasoning_summary": "Underexposed underwater portrait with strong blue-green cast."
}
```

## Parameter safety — 전부 클램프

```text
exposure -2.0..+2.0   contrast -50..+50    highlights -80..+40   shadows -40..+80
whites -50..+50       blacks -50..+50      temperature_delta -2000..+2000
tint -50..+50         vibrance -30..+60    saturation -30..+30
texture -20..+35      clarity -20..+35     dehaze 0..+35
noise_reduction 0..60 sharpening 0..80
```

클램프 발생 시: `clamped=true`, `requires_review=true`, reasoning_summary에 기록.
범위는 config에 있고 상수 산재 금지.

## Low confidence behavior

vision confidence가 낮으면: 보수적 보정값, `requires_review=true`,
극단적 색보정 회피, risk flag를 reasoning_summary에 기록.

## requires_review 전파 (sticky)

`requires_review=true`는 게이트까지 살아남는다: quality gate는 이런 task를
PASS로 확정할 수 없다 — 최선의 결과는 REVIEW_REQUIRED다.
worker가 plan → gate로 플래그를 운반하고, gate가 강제한다 (quality-gate 참조).

## Determinism

같은 VisionAnalysisResult + config → 같은 CorrectionPlan. Planner 내부 모델 호출 금지.
미지의 분석 필드는 무시하거나 기록만 하고, 절대 보정값으로 추측하지 않는다.

## Artifacts & DB

아티팩트: `correction_plan.json`, 재시도 시 `retry_history.json`.
하네스는 clamp, sticky requires_review, Lightroom 직렬화 가능성을 검증한다.
DB 요약: `correction_plans` 행 (requires_review, clamped, adjustments_jsonb 포함).

## Forbidden

미검증 raw 모델 값 적용; 이 모듈에서 vision 모델·Lightroom 호출;
여기서 PASS/FAILED 확정; Lightroom request JSON 작성 (lightroom-bridge의 일).

## Acceptance criteria

mock vision 결과로 동작; 모든 값 클램프; 저신뢰 → 보수화;
plan이 Lightroom request로 직렬화 가능; requires_review가 게이트에 도달; `run_correction_planner_test.py` 통과.
