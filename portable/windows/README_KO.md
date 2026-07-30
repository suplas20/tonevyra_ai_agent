# Tonevyra AI Windows 포터블 실행 안내

이 패키지는 설치 프로그램이 아닌 Windows x64 포터블 실행 파일 묶음입니다.

포함 항목:

- `Agent/TonevyraAI.exe`와 내장 Python 3.11 런타임
- `PlannerServer/TonevyraPlannerServer.exe`와 내장 Python 런타임
- Qwen3-VL-4B-Instruct 로컬 모델
- Lightroom Classic Plugin
- 초기화·점검·시작 PowerShell 스크립트

Python과 CUDA Toolkit은 대상 PC에 별도로 설치하지 않습니다. PostgreSQL, Lightroom
Classic, NVIDIA 드라이버 및 Microsoft Visual C++ x64 Runtime은 별도 준비가 필요합니다.

## 권장 PC

- Windows 11 64-bit
- AVX2 지원 Intel/AMD CPU
- RAM 32GB 이상
- NVIDIA GPU VRAM 16GB 이상 권장
- NVIDIA Windows 드라이버 580.88 이상
- 포터블 패키지와 작업 파일을 위한 SSD 여유 공간 25GB 이상

현재 모델은 비양자화 bfloat16 가중치이므로 Lightroom Classic과 동시에 사용할 때
VRAM 12GB 구성은 부족할 수 있습니다.

## 대상 PC 필수 설치

1. NVIDIA 그래픽 드라이버
2. Microsoft Visual C++ 2015-2022 x64 Redistributable
3. PostgreSQL 18 또는 호환되는 지원 버전
4. Adobe Creative Cloud를 통한 Lightroom Classic

Python은 실행 파일에 포함되어 있으므로 설치하지 않습니다. 소스 코드로 직접 실행할
경우에만 Python 3.11이 필요합니다.

## PostgreSQL 준비

PostgreSQL 설치 시 기억해야 할 값:

- 호스트: `127.0.0.1`
- 포트: `5432`
- 관리자 계정: `postgres`
- 설치 중 지정한 관리자 암호

pgAdmin Query Tool에서 `postgres` 계정으로 다음을 실행합니다. 암호는 실제 사용할
강한 암호로 변경합니다.

```sql
CREATE ROLE tonevyra_app LOGIN PASSWORD 'CHANGE_ME_DATABASE_PASSWORD';
CREATE DATABASE tonevyra_agent OWNER tonevyra_app;
```

이미 role 또는 DB가 존재한다면 다시 생성하지 마십시오. 기존 PostgreSQL 데이터는
삭제하거나 초기화하지 않습니다.

## 최초 1회 설정

PowerShell을 열고 압축을 푼 패키지 폴더에서 실행합니다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Initialize-Tonevyra.ps1
```

생성된 `.env` 파일에서 다음 부분을 PostgreSQL role 암호로 변경합니다.

```env
TONEVYRA_DATABASE_URL=postgresql+psycopg://tonevyra_app:실제암호@127.0.0.1:5432/tonevyra_agent
```

그 후 DB 스키마와 Lightroom Plugin을 준비합니다.

```powershell
.\scripts\Initialize-Tonevyra.ps1 -BootstrapDatabase -InstallLightroomPlugin
```

Lightroom Classic에서 `파일 > 플러그인 관리자`를 열고 `TonevyraAI.lrplugin`이 활성화되어
있는지 확인합니다.

## 실행 전 점검

```powershell
.\scripts\Check-Prerequisites.ps1
```

## 실행 순서

Planner Server를 먼저 실행합니다.

```powershell
.\scripts\Start-PlannerServer.ps1
```

그 다음 Agent를 실행합니다.

```powershell
.\scripts\Start-Agent.ps1
```

사진을 다음 폴더에 넣습니다.

```text
runtime\input
```

Planner Server를 종료할 때:

```powershell
.\scripts\Stop-PlannerServer.ps1
```

Agent는 시스템 트레이의 종료 메뉴를 사용해 먼저 종료하십시오.

## 주의

- Planner Server는 `127.0.0.1`에만 바인딩되며 외부 PC에 공개하지 않습니다.
- Agent의 모델 Worker는 네트워크를 사용하지 않습니다.
- `.env`에는 DB 암호와 Planner API 키가 있으므로 다른 사람에게 전달하지 않습니다.
- 실행 파일은 현재 Authenticode 서명이 없는 개발 빌드입니다. Windows SmartScreen
  경고가 표시될 수 있으며, 외부 배포 전 정식 코드 서명이 필요합니다.
- 다른 NVIDIA/CUDA 세대의 PC에서는 별도 호환성 빌드가 필요할 수 있습니다.
