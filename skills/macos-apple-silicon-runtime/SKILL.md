# Skill: macOS Apple Silicon Runtime

## 목적

Tonevyra 공통 Core를 변경하지 않고 Apple Silicon arm64에서 메뉴 막대 UI, FSEvents, 로그인 항목, 권한, Lightroom 경로, MPS backend를 구현한다.

## 절차

```text
1. AGENTS.md와 T-031 문서를 읽는다.
2. 플랫폼 독립 contract를 먼저 정의한다.
3. macOS 코드는 platform/macos 아래로 격리한다.
4. 메뉴 막대 Shell은 모델을 import하지 않는다.
5. FSEvents 후 반드시 rescan/stability/dedup를 실행한다.
6. 폴더 접근 거부를 명시적 오류로 기록한다.
7. MPS 가용성, 실제 모델 로드, 실제 이미지 추론을 각각 증명한다.
8. arm64 실기기 evidence 없이 완료를 선언하지 않는다.
```

## 금지

```text
- Rosetta를 기본 경로로 사용
- silent CPU fallback
- 모든 디스크에 Full Disk Access 강제
- FSEvents event당 즉시 job 생성
- Windows 코드 복사본을 별도 제품으로 유지
```

## 완료 증거

```text
architecture evidence
menu bar screenshot
FSEvents ingest evidence
MPS inference evidence
Lightroom bridge evidence
10-image memory soak
```
