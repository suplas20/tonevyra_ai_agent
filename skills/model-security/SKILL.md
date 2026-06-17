---
name: model-security
description: Local-only, network-blocked, replaceable vision model runtime, model worker isolation, hardware profiles, and the model policy. Use this skill before touching model loading, Hugging Face/Transformers, ModelScope, GGUF/AWQ runtime, model worker execution, network settings, model paths, benchmark logic, or backend selection.
---

# Model Security & Model Policy

## Model policy

```text
VisionModelBackend
  ├─ MockVisionBackend              # 개발/CI 기본. 항상 먼저 통과
  ├─ Qwen25VLBackend                # stable default: Qwen2.5-VL-3B-Instruct 4bit
  ├─ Qwen3VLBackend                 # validation candidate: Qwen3-VL-4B 4bit, opt-in only
  └─ FutureAlternativeBackend       # 교체 가능 설계 유지
```

- 기본값은 Qwen2.5-VL-3B 4bit이다.
- Qwen3-VL-4B는 검증 후보이며 config의 명시적 opt-in으로만 활성화한다.
- Qwen3-VL-4B는 Windows와 Mac mini 24GB에서 Lightroom Classic과 동시에 benchmark를 통과한 뒤에만 기본값 승격을 검토한다.
- Qwen2.5-VL-7B / Qwen3-VL-8B 이상은 quality mode 옵션이다. MVP 기본값·필수값으로 만들지 않는다.
- 어떤 모델도 hard dependency가 아니다. backend는 비활성화·교체 가능해야 한다.
- `vision/model.py` 또는 `vision/backends/` 밖의 코드는 특정 모델을 가정하면 안 된다.

## Hardware policy

```text
Minimum development profile:
  Windows RAM 16GB / VRAM 8GB
  MockVisionBackend 또는 constrained Qwen2.5-VL-3B 테스트 가능
  Lightroom + local VLM의 여유 구동 보장 아님

Stable MVP profile:
  Windows RAM 32GB / VRAM 8GB+
  Mac mini 24GB unified memory
  Qwen2.5-VL-3B 4bit + Lightroom Classic 동시 운용 목표

Validation candidate profile:
  Qwen3-VL-4B 4bit
  Lightroom 실행 상태 benchmark 통과 필요

Quality profile:
  Qwen2.5-VL-7B / Qwen3-VL-8B
  고사양 전용, Mac mini 24GB 기본값 금지
```

모델 파일 크기를 런타임 메모리 추정치로 쓰지 않는다. 실제 사용량은 모델 weight, vision encoder, processor/tokenizer, image tensor, KV cache, framework overhead, Python process memory, Lightroom memory까지 포함해 측정해야 한다.

Backend-specific runtime options such as `mmproj`, GGUF projection settings, context size, KV-cache quantization, AWQ-specific loader options, or Metal/CUDA-specific flags must live in backend-specific config/implementation. Do not place those settings in global model policy unless the runtime is explicitly fixed.

## Data privacy rule

사진, preview, 프롬프트, 메타데이터, raw response, 구조화 분석, 보정 결과, 품질 결과 — 어떤 것도 외부 서비스로 전송 금지. 예외 없음.

## Local-only loading

```text
- 로컬 모델 파일만 사용
- local_files_only=True 필수
- trust_remote_code=True 금지
- safetensors 또는 검증된 GGUF 선호
- 모델 revision/version 고정
- 모델 파일 hash 기록
- 모델은 models/ 또는 설정된 로컬 model root 아래에만
- hub/online 동작·텔레메트리 비활성화
```

Env vars:

```bash
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
```

env vars만으로는 부족하다. 모델 워커는 OS 방화벽 outbound 차단이 가능한 구조여야 한다.

## Allowed model sources for installation

모델 설치 단계에서만 네트워크 다운로드가 허용된다. 허용 소스:

```text
- Hugging Face official Qwen organization
- ModelScope official Qwen organization
```

실행 단계에서는 로컬 모델 경로만 사용한다.

## Model worker isolation

```text
Python Agent → local model worker process → local model files
```

워커가 접근 가능한 경로:

```text
runtime/previews/
runtime/artifacts/
models/ 또는 configured local model root
```

광범위 파일시스템 접근, 네트워크 접근, 외부 URL 입력 금지.

## Runtime model input

```text
1024px sRGB JPEG preview + EXIF/basic metadata
```

원본 RAW를 모델에 직접 전달 금지.

## Prohibited

```text
처리 중 모델 다운로드
원격 API 호출
외부 URL 이미지 로딩
trust_remote_code=True
사용자 데이터 포함 텔레메트리
런타임 자동 업데이트
임의 파일시스템 접근
Correction Planner 미검증 최종 Lightroom 값
```

## Required runtime checks

```text
모델 경로 존재 + 허용된 로컬 root 내부
오프라인 env vars 설정
local_files_only 사용
trust_remote_code 부재
입력 이미지가 에이전트가 생성한 로컬 preview 경로
활성 backend가 하드웨어 프로필에 적합한지 확인
부족하면 경고, 차단, 또는 작은 backend로 강등
```

## Benchmark gate for Qwen3

Qwen3-VL-4B를 default로 승격하려면 최소 다음을 통과해야 한다.

```text
- Windows stable profile에서 Lightroom 실행 상태 100장 smoke benchmark 통과
- Mac mini 24GB에서 Lightroom 실행 상태 100장 smoke benchmark 통과
- OOM 없음
- 모델 worker crash 없음
- 평균/최악 추론 시간이 config 허용 범위 내
- PASS/REVIEW/FAILED pipeline 결과가 Mock/Fake 기준과 구조적으로 일관
- security harness 통과
```

## Guardrails

- 이 규칙과 충돌하는 구현 요청은 구현하지 말고 멈춰서 충돌을 보고한다.
- Qwen3 후보 구현 시에도 보안 하네스와 benchmark harness를 함께 갱신한다.

## Acceptance criteria

Mock backend가 실제 backend보다 먼저 동작; backend 교체·비활성화 가능; 처리 중 네트워크 불필요; raw response 아티팩트 저장(프라이버시 모드 제외); 구조화 출력은 사용 전 검증; stable MVP profile에서 기본 backend 동작; Qwen3는 benchmark 전 default가 아님.
