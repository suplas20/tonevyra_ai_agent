# Tonevyra AI Windows 포터블 실행 가이드

## 배포 방식

Tonevyra AI Agent와 Planner Server는 별도 Windows 프로세스로 실행한다.

```text
TonevyraAI.exe
→ 로컬 Qwen 분석
→ http://127.0.0.1:8000
→ TonevyraPlannerServer.exe
→ CorrectionPlan 응답
→ Lightroom Classic Plugin
```

Agent 실행 파일에는 Python 3.11, PyTorch, Transformers 등 실행 라이브러리가 포함된다.
Qwen 모델 가중치는 실행 파일 내부가 아닌 포터블 패키지의 `models/` 폴더에 포함한다.

## 대상 PC 필수 구성

| 항목 | 필요 여부 | 설명 |
|---|---:|---|
| Python | 불필요 | 실행 파일에 Python 3.11 런타임 포함 |
| CUDA Toolkit | 불필요 | PyTorch CUDA 런타임 포함, NVIDIA 드라이버는 필요 |
| NVIDIA 드라이버 | 필수 | 현재 CUDA 13.0 빌드 기준 Windows 580.88 이상 권장 |
| PostgreSQL | 필수 | `tonevyra_agent` DB와 `tonevyra_app` role 필요 |
| Lightroom Classic | 필수 | 실제 보정 및 export 실행 |
| Visual C++ x64 Runtime | 권장/사실상 필수 | 최신 2015-2022 호환 런타임 |

공식 설치 위치:

- PostgreSQL Windows: https://www.postgresql.org/download/windows/
- Lightroom Classic 요구사항: https://helpx.adobe.com/lightroom-classic/system-requirements.html
- NVIDIA 드라이버: https://www.nvidia.com/Download/index.aspx
- Visual C++ x64 Runtime: https://aka.ms/vs/17/release/vc_redist.x64.exe

## 빌드

```powershell
.\.venv\Scripts\python.exe harness\scripts\build_tonevyra_windows_exe.py

.\.venv\Scripts\python.exe harness\scripts\build_tonevyra_planner_server_exe.py `
  --output-dir runtime\windows_dist\TonevyraPlannerServer

.\.venv\Scripts\python.exe harness\scripts\build_tonevyra_windows_portable.py `
  --model-source D:\Tonevyra\models\Qwen3-VL-4B-Instruct
```

산출물:

```text
runtime/portable_windows/TonevyraAI-Portable-<version>/
```

세부 사용 방법은 산출물 안의 `README_KO.md`를 따른다.

## 출시 제한

현재 빌드는 Authenticode 서명이 없는 개발 빌드다. 다른 PC에서 기능 검증은 가능하지만,
일반 고객 배포 전에는 코드 서명, 대상 GPU 실기기 모델 로딩, Lightroom Classic 동시
실행 및 PostgreSQL 복구 테스트가 필요하다.
