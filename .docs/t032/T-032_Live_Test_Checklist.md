# T-032 Planner API Live Test Checklist

## 환경 기록

```text
Client OS/build:
Agent build SHA-256:
Planner server host/build SHA-256:
Planner version:
Policy version:
API schema versions:
TLS certificate issuer/expiry:
Oracle shape / CPU / RAM:
Nginx version:
Python/FastAPI/Uvicorn versions:
```

## Client build separation

- [ ] 배포 client wheel/exe/app bundle에 Planner rule module이 없다.
- [ ] legacy local Planner를 production config로 선택할 수 없다.
- [ ] Fake/Mock Planner는 test build에서만 선택 가능하다.

## Privacy

- [ ] captured request body에 original/preview image bytes가 없다.
- [ ] filename, local path, GPS, camera serial, user/customer name이 없다.
- [ ] prompt와 raw model response가 없다.
- [ ] Authorization/API key가 client artifact 또는 logs에 없다.
- [ ] server logs에 secret/full payload가 없다.

## API/security

- [ ] HTTP가 HTTPS로 강제되거나 차단된다.
- [ ] TLS certificate verification을 끄지 않는다.
- [ ] 잘못된/missing key는 401/403이다.
- [ ] valid key만 Planner를 실행한다.
- [ ] oversized body가 413으로 거부된다.
- [ ] unsupported schema가 Planner 실행 전에 거부된다.
- [ ] production OpenAPI/Swagger가 비활성화 또는 보호된다.

## Contract/integrity

- [ ] valid request가 bounded CorrectionPlan을 반환한다.
- [ ] response request_id와 input_digest가 일치한다.
- [ ] client recomputed plan_digest가 일치한다.
- [ ] response schema/version mismatch가 Lightroom에 도달하지 않는다.
- [ ] forbidden command/path field가 있는 response가 거부된다.

## Idempotency/recovery

- [ ] same key + same payload가 같은 plan_digest를 반환한다.
- [ ] replay response에 replayed=true가 기록된다.
- [ ] same key + different payload가 409이다.
- [ ] timeout/503/429 재시도가 bounded다.
- [ ] 401/403/409/422는 무한 재시도하지 않는다.
- [ ] server restart 후 같은 key replay가 중복 Lightroom 효과를 만들지 않는다.
- [ ] client restart 후 persisted request에서 재개한다.
- [ ] retry exhaustion 시 local Planner fallback이 없다.

## Soak/performance

- [ ] 3000개 순차 request_id가 모두 고유하다.
- [ ] 3000개 응답이 누락 없이 대응한다.
- [ ] duplicate external Lightroom effect가 0이다.
- [ ] server OOM/restart/crash가 없다.
- [ ] latency/error/retry statistics가 evidence에 기록된다.
- [ ] Uvicorn worker와 Planner execution concurrency가 정책값을 초과하지 않는다.

## Regression

- [ ] T-019~T-031 static/runtime regression이 통과한다.
- [ ] Windows tray/macOS menu bar가 API disconnected 상태를 명확히 표시한다.
- [ ] local Qwen and idle GPU lifecycle behavior가 유지된다.
- [ ] Lightroom apply/export/quality contracts가 유지된다.

## 필수 첨부

```text
t032_implementation_runtime_evidence.json
t032_live_server_evidence.json
t032_client_build_scan.json
t032_request_capture_redacted.json
t032_3000_sequential_soak.json
t032_restart_replay_evidence.json
t032_tls_evidence.json
```
