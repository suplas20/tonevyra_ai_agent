# T-033 Codex 작업 프롬프트

다음 문서와 계약을 먼저 읽고 T-033을 구현하라.

```text
AGENTS.md
CLAUDE.md
.docs/t033/T-033_Cross_Platform_Installer_Packaging_Work_Order.md
.docs/t033/T-033_Implementation_Specification.md
.docs/t033/T-033_Dependency_Distribution_and_License_Policy.md
.docs/t033/T-033_Windows_Installer_Guide.md
.docs/t033/T-033_macOS_Installer_Guide.md
.docs/t033/T-033_Live_Test_Checklist.md
harness/CONTRACT_T033_CROSS_PLATFORM_INSTALLER.md
skills/T033_SKILL_INVENTORY.json
```

## 구현 목표

Windows x64와 macOS Apple Silicon arm64에서 Tonevyra AI를 설치·복구·업그레이드·제거할 수 있는 제품 설치 패키지를 구현한다.

## 하드 요구사항

```text
- Preserve every T-032 file and all 51 baseline skills.
- Add exactly seven T-033 skills; cumulative total 58.
- Bundle Python 3.11.9 and locked dependencies.
- Never depend on or mutate system Python.
- Do not bundle any PostgreSQL installer/package.
- Download the latest stable GA PostgreSQL installer from approved official sources.
- Reject alpha/beta/RC/snapshot/nightly releases.
- Verify signed channel metadata, URL host, SHA-256 and publisher/package signature.
- Preserve existing PostgreSQL installations and user data.
- Do not bundle or automate Adobe Lightroom Classic installation.
- Keep T-032 Planner service/rules out of the client package.
- Sign Windows release artifacts.
- Sign, notarize and staple macOS release artifacts.
- Reference harness evidence is not strict completion.
```

## 구현 순서

1. 현재 런타임/의존성/빌드 스캔
2. 잠금 파일과 라이선스 inventory 생성
3. 공통 dependency/install state 모듈
4. Python 3.11.9 bundled build
5. PostgreSQL stable resolver/downloader/verifier
6. DB bootstrap/migration/receipt
7. Windows bootstrapper and release signing
8. macOS bundle/PKG/DMG signing and notarization
9. Lightroom detection/plugin installation
10. repair/upgrade/uninstall
11. deterministic harness evidence
12. real Windows/macOS live evidence
13. T-019..T-032 regression execution

## 완료 전 실행

```text
python harness/scripts/verify_t033_cross_platform_installer.py --project-root .
python harness/scripts/run_t033_installer_reference.py --project-root . --output runtime/evidence/t033/reference_runtime_evidence.json
python harness/scripts/verify_t033_cross_platform_installer.py --project-root . --runtime-evidence runtime/evidence/t033/reference_runtime_evidence.json
```

Strict gate:

```text
python harness/scripts/verify_t033_cross_platform_installer.py \
  --project-root . \
  --runtime-evidence <implementation-runtime.json> \
  --windows-evidence <windows-live.json> \
  --macos-evidence <macos-live.json> \
  --artifact-scan <artifact-scan.json> \
  --strict
```

실제 서명 인증서나 Apple 계정이 없어 strict evidence를 만들 수 없는 경우, 정적/참조 구현까지만 완료하고 strict 완료를 주장하지 말라.
