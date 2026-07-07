# T-032 문서·하네스·스킬 업데이트 보고서

## 기준

```text
Baseline: T-031
Baseline skills: 47
Added skills: 4
T-032 total: 51
```

기존 파일과 47개 스킬을 삭제·병합·이름 변경하지 않았다.

## 추가 스킬

```text
planner-api-contract
planner-api-client
planner-api-service
planner-api-security
```

## 추가 문서

```text
.docs/t032/T-032_Planner_Engine_API_Separation_Work_Order.md
.docs/t032/T-032_Implementation_Specification.md
.docs/t032/T-032_API_Contract.md
.docs/t032/T-032_Server_Deployment_Guide.md
.docs/t032/T-032_Live_Test_Checklist.md
.docs/t032/T-032_Codex_Prompt.md
```

## 하네스

```text
T-032 contract and env example
request/response/error/runtime/live/build/soak schemas
privacy, digest, retry, version, idempotency, soak fixtures
static/strict verifier
reference runtime generator
HTTPS live probe
machine-readable manifest and skill inventory
```

## 주요 정책 변경

```text
- 기존 완전 로컬/원격 금지 규칙을 T-032 단일 Planner API 예외로 명시
- 원본/preview/Qwen/Lightroom/export/quality는 로컬 유지
- 최소화된 분석 JSON만 HTTPS로 전송
- production client에서 Planner rules/local fallback 제거
- 기존 image_tasks status 유지
- durable request + digest + idempotency 기반 재시도/복구
- reference evidence와 strict live completion 분리
```

## Strict 완료 증거

```text
implementation runtime evidence
live HTTPS server evidence
production client build scan
3000 sequential request soak
T-019 through T-031 regressions
```

## 파일 보존 검증

원본 압축본과 비교한 결과:

```text
원본 파일: 393
최종 파일: 426
추가: 33
수정: 36
삭제: 0
```

기존 `__pycache__`를 포함한 모든 원본 파일을 유지했다.

## 누적 회귀 검증기 호환성

T-029, T-030, T-031 검증기가 이후 티켓의 추가 스킬을 실패로 오인하지 않도록, 각 티켓의 스킬 inventory snapshot은 그대로 검증하면서 현재 누적 스킬 수가 더 큰 경우를 허용하도록 수정했다.
