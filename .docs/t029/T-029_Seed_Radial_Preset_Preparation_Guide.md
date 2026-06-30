# T-029 Seed Radial Preset 준비 가이드

## 0. Deprecated By 2026-06-29 Scope Update

방사형 그레이디언트 / `radial_template` fallback은 T-029 범위에서 제외되었다.

이 가이드는 historical reference로만 남긴다. 현재 T-029 작업에서 seed radial preset을 만들거나, template generator를 실행하거나, radial template manifest를 runtime dependency로 사용하지 않는다.

## 1. 목적

T-029 template generator는 지원 대상 Lightroom Classic 버전에서 실제로 생성된 radial-gradient preset을 seed로 사용한다. 이 단계는 Lightroom 내부 마스크 구조를 추측해 만드는 위험을 피하기 위한 1회성 준비 작업이다.

## 2. 준비 원칙

```text
지원 Lightroom Classic 버전을 먼저 고정한다.
테스트 전용 사진에서 radial gradient 1개를 만든다.
위치·크기·페더가 명확한 기준값을 사용한다.
다른 AI mask, brush, color range, 사용자 개인정보를 포함하지 않는다.
preset을 로컬 파일로 저장/내보낸다.
원본 seed를 수정하지 않고 checksum을 고정한다.
```

## 3. 권장 기준 geometry

seed는 generator가 안전하게 식별할 수 있도록 중앙의 단순한 세로 타원으로 만든다.

```text
center_x: 약 0.5
center_y: 약 0.5
aspect: vertical
size: medium
rotation: 0
feather: high baseline
```

정확한 내부 값은 export된 preset과 실제 Lightroom 재적용 결과에서 확인한다.

## 4. 기준 adjustment

완전히 0인 로컬 adjustment는 preset에서 생략될 수 있으므로, 지원 버전의 동작을 확인할 수 있는 작고 안전한 sentinel 값을 사용한다.

```text
예: Exposure +0.01 또는 동등한 최소 식별값
```

sentinel 값은 최종 사진 보정값이 아니다. Plugin이 실제 bounded local values를 적용하거나, template generation 단계에서 승인된 방식으로 교체해야 한다. Sentinel이 최종 export에 남는지 반드시 검증한다.

## 5. 저장 위치 예시

```text
lightroom/TonevyraAI.lrplugin/Resources/radial_masks/seeds/
  radial_seed_<verified-lightroom-version>.xmp
  radial_seed_<verified-lightroom-version>.metadata.json
```

metadata 예시:

```json
{
  "seed_id": "radial-seed-v1",
  "lightroom_version": "<VERIFIED_VERSION>",
  "source_file": "radial_seed_<verified-lightroom-version>.xmp",
  "sha256": "<64-hex>",
  "geometry_description": "centered medium vertical radial, rotation 0, high feather",
  "sentinel_adjustment": {
    "name": "Exposure",
    "value": 0.01
  },
  "created_by": "human operator",
  "validated_reapply": false
}
```

## 6. Phase 0 검증

seed를 generator에 넣기 전에 Plugin 경로에서 그대로 재적용한다.

```text
[ ] Plugin이 preset을 자동 적용함
[ ] 사용자 드래그가 필요하지 않음
[ ] center/size/aspect/rotation/feather가 유지됨
[ ] sentinel 또는 intended local setting이 확인됨
[ ] result JSON과 before/after snapshot이 남음
[ ] 같은 request replay에 duplicate가 없음
[ ] 사용자 마스크가 유지됨
```

`validated_reapply=true`는 위 항목의 실제 evidence가 있을 때만 기록한다.

## 7. 금지

```text
인터넷에서 출처가 불명확한 preset을 seed로 사용
모델이 생성한 임의 XMP를 검증 없이 사용
지원 버전이 다른 seed를 그대로 재사용
사용자 사진의 기존 개인 마스크를 seed에 포함
seed checksum 없이 library 배포
```

## 8. Codex 전달 정보

Codex 구현 시작 시 다음 값을 제공하거나 프로젝트 파일로 배치한다.

```text
seed preset path
seed SHA-256
검증된 Lightroom Classic 버전
Phase 0 request/result/screenshot 경로
template library output root
```

seed가 없으면 Codex는 bulk template 생성으로 진행하지 않고 `BLOCKED_RADIAL_SEED_MISSING`으로 중단해야 한다.
