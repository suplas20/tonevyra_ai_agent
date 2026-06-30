# T-030 Tonevyra System Tray Icon Asset Guide

## 1. 목적

Tonevyra Windows system tray에 사용할 생산용 아이콘 자산의 입력, 변환, 검증 기준을 정의한다.

## 2. 사용 심벌

브랜드 가이드의 다음 요소만 사용한다.

```text
Tonevyra 원형 조리개 심벌 + 작은 별
```

작은 tray 영역에서 글자는 식별되지 않으므로 `Tonevyra AI` 워드마크는 포함하지 않는다.

## 3. 원본 요구사항

우선순위:

```text
1. 승인된 SVG
2. 투명 배경 1024×1024 이상 PNG
3. 승인된 벡터 PDF/AI에서 내보낸 SVG/PNG
```

금지:

```text
- 화면 캡처 crop
- Google Drive 미리보기 이미지 crop
- JPEG 로고
- 낮은 해상도 확대
- 배경이 포함된 로고 시트 전체
```

현재 제공된 화면 캡처는 디자인 참고용이며 production source가 아니다.

## 4. 필요한 산출물

```text
resources/branding/source/tonevyra_symbol.svg
resources/branding/windows/tonevyra_tray.ico
resources/branding/windows/tonevyra_tray_processing.ico
resources/branding/windows/tonevyra_tray_warning.ico
resources/branding/windows/tonevyra_tray_error.ico
resources/branding/windows/tray_icon_manifest.json
```

단일 ICO에 포함할 크기:

```text
16×16
20×20
24×24
32×32
40×40
48×48
64×64
128×128
256×256
```

## 5. 작은 크기 최적화

```text
- 16~24px에서 aperture blade가 뭉개지지 않도록 optical correction
- 별이 1px noise처럼 보이지 않도록 크기/간격 조정
- 투명 padding 일관성
- 얇은 선 제거
- Windows 자동 축소만 믿지 않고 핵심 크기를 직접 검수
```

원본 로고를 변형하지 않되 작은 픽셀용 hinting/optical variant는 브랜드 승인 후 사용할 수 있다.

## 6. 상태 아이콘

기본 로고를 유지하고 우측 하단 badge를 추가한다.

```text
processing: 작은 activity badge 또는 저속 프레임
warning/paused/degraded: warning badge
error: error badge
```

브랜드 가이드의 semantic color를 사용하되 작은 영역에서 대비를 검증한다. 색상만으로 상태를 구분하지 말고 badge shape도 다르게 한다.

## 7. Manifest

```json
{
  "schema_version": "t030.tray_icon_manifest.v1",
  "brand": "Tonevyra AI",
  "source_asset": "resources/branding/source/tonevyra_symbol.svg",
  "source_sha256": "...",
  "approved": true,
  "icons": [
    {
      "state": "WATCHING",
      "path": "resources/branding/windows/tonevyra_tray.ico",
      "sha256": "...",
      "sizes": [16, 20, 24, 32, 40, 48, 64, 128, 256]
    }
  ]
}
```

## 8. 검증

```text
[ ] source asset approved
[ ] source hash fixed
[ ] all required ICO sizes present
[ ] transparency correct
[ ] Windows light theme visible
[ ] Windows dark theme visible
[ ] 100/125/150/200% DPI visible
[ ] no wordmark in tray
[ ] no screenshot-derived asset
[ ] installer/resource path stable
```

## 9. 차단 조건

승인된 원본 자산이 없거나 ICO 검증이 실패하면:

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
```

임시 아이콘으로 기능 테스트는 가능하지만 T-030 production completion을 선언하지 않는다.
