# T-033 — macOS 설치 프로그램 가이드

## 1. 지원 범위

```text
OS: T-031에서 검증된 macOS 범위
Architecture: Apple Silicon arm64
Distribution: Developer ID outside Mac App Store
```

## 2. 패키지 구조

```text
TonevyraAI.app/
└─ Contents/
   ├─ MacOS/
   ├─ Frameworks/
   ├─ Resources/
   │  ├─ Lightroom plugin
   │  └─ Licenses
   └─ Helpers/
```

Python 3.11.9와 네이티브 의존성은 앱 번들 내부에 포함한다. 시스템 `/usr/bin/python3`, Homebrew Python 또는 사용자의 pyenv를 사용하지 않는다.

## 3. 서명 순서

```text
nested dylibs/frameworks/helpers
→ main executable
→ .app bundle
→ verify codesign
→ build flat .pkg
→ sign with Developer ID Installer
→ submit with notarytool
→ wait for Accepted
→ staple ticket
→ Gatekeeper assessment
```

DMG를 제공하는 경우 최종 DMG도 서명·공증 정책을 따른다.

## 4. PostgreSQL

PostgreSQL 설치 패키지는 Tonevyra PKG/DMG 내부에 포함하지 않는다. 설치 과정에서 Apple Silicon을 지원하는 최신 안정화 설치 파일을 공식 경로에서 다운로드하고, 패키지 서명·해시·출처를 검증한다.

관리자 인증은 macOS 표준 인증 흐름을 사용한다. 비밀번호를 Tonevyra UI, shell argument, 환경 변수 또는 로그에 기록하지 않는다.

## 5. 자동 시작

T-031의 menu bar/Worker 경계를 유지하고, 승인된 Login Item 또는 LaunchAgent를 사용한다. root LaunchDaemon으로 Agent business logic을 실행하지 않는다.

## 6. Gatekeeper 검증

```bash
codesign --verify --deep --strict --verbose=2 TonevyraAI.app
spctl --assess --type execute --verbose=4 TonevyraAI.app
pkgutil --check-signature TonevyraAI.pkg
xcrun stapler validate TonevyraAI.app
xcrun stapler validate TonevyraAI.pkg
```

`--deep`은 검증 보조용이며 서명 전략을 대신하지 않는다. 실제 서명은 내부 구성요소부터 수행한다.

## 8. macOS 올인원 설치 흐름

사용자는 PKG 실행, 설치 클릭, macOS 관리자 인증 외에 별도 설정을 하지 않는다.

```text
signed/notarized PKG verification
→ app payload install
→ bundled Python 3.11.9 verification
→ PostgreSQL detection
→ approved stable PostgreSQL package download and signature/hash verification
→ unattended/installer-controlled PostgreSQL installation
→ service readiness wait
→ automatic Role/DB creation
→ Alembic upgrade head
→ schema/read-write verification
→ Keychain credential storage
→ Lightroom detection/plugin install or PENDING
→ LaunchAgent/Login Item registration
→ post-install doctor
→ receipt commit
```

Homebrew 설치나 Terminal 명령 실행을 사용자에게 요구하지 않는다.
