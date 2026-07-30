# T-033 — 필수 구성요소 배포·라이선스 정책

## 1. 목적

이 문서는 설치 패키지에 포함하는 파일과 설치 시 다운로드하는 파일을 구분하고, 구성요소별 재배포 검토 결과를 추적하는 형식을 정의한다. 법률 자문을 대체하지 않으며, 출시 전 최종 라이선스 검토를 요구한다.

## 2. 분류

```text
BUNDLED_APPROVED
BUNDLED_REVIEW_REQUIRED
DOWNLOAD_OFFICIAL
EXTERNAL_USER_MANAGED
FORBIDDEN
```

## 3. T-033 기본 분류

| 구성요소 | 분류 | 조건 |
|---|---|---|
| Python 3.11.9 runtime | BUNDLED_APPROVED | PSF 및 포함 고지 유지 |
| Python packages | BUNDLED_REVIEW_REQUIRED | 각 패키지 라이선스/NOTICE 검토 |
| Tonevyra source/binaries | BUNDLED_APPROVED | 자사 구성요소 |
| PostgreSQL installer | DOWNLOAD_OFFICIAL | 패키지에 내장하지 않음 |
| DB migrations | BUNDLED_APPROVED | 자사 구성요소 |
| Lightroom plugin | BUNDLED_APPROVED | 자사 구성요소 및 사용 SDK 조건 검토 |
| Lightroom Classic | EXTERNAL_USER_MANAGED | Adobe 계정·구독 필요 |
| Creative Cloud | EXTERNAL_USER_MANAGED | Adobe 배포물 |
| Qwen model weights | BUNDLED_REVIEW_REQUIRED | 정확한 모델 revision 라이선스 기준 |
| GPU driver | EXTERNAL_USER_MANAGED | 제조사 배포 및 시스템 종속 |
| Planner rules/service | FORBIDDEN in client | T-032 server-only boundary |

## 4. third-party manifest

모든 내장 바이너리는 다음 정보를 가진다.

```json
{
  "name": "example",
  "version": "1.2.3",
  "source_url": "https://official.example/",
  "artifact_sha256": "<64-hex>",
  "license_id": "SPDX-or-reviewed-name",
  "license_file": "licenses/example/LICENSE.txt",
  "notice_file": "licenses/example/NOTICE.txt",
  "distribution_mode": "BUNDLED_APPROVED",
  "reviewed_by": "<name-or-role>",
  "reviewed_at": "<ISO-8601>",
  "review_evidence": "<ticket/path>",
  "source_offer_required": false
}
```

`reviewed_by`, `reviewed_at`, `license_file`가 비어 있는 `BUNDLED_APPROVED` 항목은 출시 빌드에 포함할 수 없다.

## 5. PostgreSQL 특별 규칙

PostgreSQL 설치 프로그램은 다운로드 전용이다.

```text
- final installer payload scan must report zero PostgreSQL installer executables/packages
- official source metadata must be persisted
- downloaded artifact hash/signature evidence must be recorded
- third-party installer terms must be shown or linked before execution when required
- downloaded installer must not be redistributed as part of Tonevyra package/cache
```

Tonevyra 설치 로그에 PostgreSQL 라이선스/출처 정보를 기록하되, 원본 설치 파일 자체는 성공 후 삭제한다.

## 6. 라이선스 출력

설치 후 사용자가 다음 위치에서 제3자 고지를 확인할 수 있어야 한다.

```text
Windows: installation directory / licenses + application About/Open Source Notices
macOS: app bundle Resources/Licenses + application About/Open Source Notices
```

## 7. 출시 게이트

```text
all bundled entries reviewed
all license files present
all NOTICE obligations satisfied
all hashes match payload
no forbidden component in client
PostgreSQL installer absent from packaged payload
license inventory generated reproducibly
```

## 9. 올인원 설치와 제3자 설치 고지

PostgreSQL 설치 파일은 Tonevyra payload에 포함하지 않지만, Tonevyra 설치 프로그램이 같은 설치 세션에서 공식 배포본을 자동 다운로드·검증·무인 설치할 수 있다.

사용자에게 PostgreSQL 설치 마법사를 직접 조작하도록 요구하지 않는다. 설치 전 다음 사실과 적용 라이선스를 고지한다.

```text
- PostgreSQL은 제3자 오픈소스 데이터베이스 구성요소다.
- 공식 배포처에서 설치 중 다운로드된다.
- 로컬 Tonevyra 작업 복구와 운영 메타데이터에 사용된다.
- 외부 네트워크에 DB 포트를 공개하지 않는다.
```

다운로드와 자동 설치는 재배포와 구분되며, 설치 파일은 검증 후 실행하고 성공 후 임시 저장소에서 삭제한다.
