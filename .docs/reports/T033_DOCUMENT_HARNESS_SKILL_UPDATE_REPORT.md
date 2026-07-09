# T-033 문서·하네스·스킬 업데이트 보고서

## 기준

```text
Baseline: T-032
Baseline skills: 51
Added skills: 7
T-033 total: 58
```

기존 51개 스킬과 기존 파일을 삭제·병합·이름 변경하지 않았다.

## 확정 배포 정책

```text
Python 3.11.9: installer/application payload에 내장
PostgreSQL installer: 내장하지 않음
PostgreSQL: 설치 시 latest stable GA 다운로드 + 서명/해시 검증
Lightroom Classic: 외부 사용자 관리, 설치 여부만 검사
Windows: signed installer
macOS: signed + notarized + stapled package
```

## 추가 스킬

```text
bundled-runtime-distribution
cross-platform-installer-packaging
dependency-detection-compatibility
installer-download-integrity
installer-upgrade-repair-uninstall
platform-signing-notarization
postgresql-bootstrap-installation
```

## 추가 문서

```text
.docs/t033/T-033_Cross_Platform_Installer_Packaging_Work_Order.md
.docs/t033/T-033_Implementation_Specification.md
.docs/t033/T-033_Dependency_Distribution_and_License_Policy.md
.docs/t033/T-033_Windows_Installer_Guide.md
.docs/t033/T-033_macOS_Installer_Guide.md
.docs/t033/T-033_Live_Test_Checklist.md
.docs/t033/T-033_Codex_Prompt.md
```

## 하네스

```text
T-033 contract/env/manifest
six JSON schemas
positive/negative dependency and PostgreSQL fixtures
static/reference/strict verifier
reference evidence generator
Windows and macOS live probe templates
T033 skill inventory
```

## 파일 보존

```text
원본 파일 수: 426
최종 파일 수: 462
추가/수정 후 삭제 파일 수: 0
```

## 완료 주의

현재 산출물은 T-033 구현을 위한 문서·하네스·스킬 계약이다. 실제 설치 프로그램, Windows 서명, macOS 공증, PostgreSQL 다운로드 설치 및 실장비 증거가 생성되기 전에는 T-033 strict 완료가 아니다.
