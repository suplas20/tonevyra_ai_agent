# T-032 — Planner Engine API Separation 작업 지시서

## 1. 문서 상태

```text
Ticket: T-032
Title: Planner Engine API Separation
Baseline: T-031 macOS Runtime and GPU Memory Lifecycle
Client: Tonevyra AI Agent on Windows/macOS
Server: Tonevyra Planner Service
Primary API style: HTTPS JSON REST
Reference framework: FastAPI + Uvicorn
Reference test host: Oracle Cloud 1 OCPU / 1GB RAM
Depends on: T-021, T-022, T-028, T-030, T-031
```

## 2. 목표

> 로컬 Agent에 포함된 Correction Planner 핵심 판단 로직을 별도 서버 프로세스로 분리하고, 로컬 Qwen 분석 결과를 최소화·검증한 JSON으로 전송하여 서버가 보정 계획을 반환하도록 구현한다.

T-032 이후 제품 경계는 다음과 같다.

```text
Local Agent
├─ folder watcher / PostgreSQL durable task state
├─ preview generation / local Qwen analysis
├─ Planner API client / retry / recovery
├─ Lightroom bridge / export / quality gate
└─ no production Planner rules

Planner Service
├─ request authentication and validation
├─ correction planner rules and policy versions
├─ bounded plan generation
├─ idempotency and response integrity evidence
└─ health / readiness / version endpoints
```

## 3. 핵심 원칙

1. 원본 사진, preview 이미지, Lightroom export, 로컬 파일 경로, 프롬프트, raw model response는 서버로 전송하지 않는다.
2. 서버로 전송 가능한 정보는 정규화된 분석 결과와 보정 판단에 필요한 최소 이미지 문맥뿐이다.
3. GPS, 카메라 일련번호, 사용자명, 고객명, 파일명, 폴더 경로는 요청에서 제거한다.
4. 로컬 배포본에는 production Planner 규칙·가중치·정책 테이블을 포함하지 않는다.
5. 모델은 계속 로컬에서 실행한다. T-032는 Qwen 원격화 작업이 아니다.
6. Planner API 실패 시 Lightroom 보정을 진행하지 않는다.
7. production에서 로컬 Planner로 자동 fallback하지 않는다.
8. 재시도는 bounded이고 PostgreSQL 작업 상태와 이벤트를 근거로 재개한다.
9. 동일 idempotency key와 동일 payload digest는 동일 결과를 반환해야 한다.
10. 같은 idempotency key에 다른 payload digest가 오면 `409 IDEMPOTENCY_CONFLICT`로 거부한다.

## 4. 표준 흐름

```text
stable photo
→ local preview
→ local VisionModelBackend analysis
→ normalized/privacy-scrubbed PlannerRequest
→ local durable request artifact + digest
→ HTTPS Planner API
→ auth/schema/version/input digest validation
→ server Planner execution
→ CorrectionPlan response + planner/policy version + plan digest
→ local response validation
→ correction_plan.json atomic save/register
→ CORRECTION_PLANNED
→ Lightroom apply/export/quality
```

## 5. API 범위

필수 endpoint:

```text
POST /api/v1/plans
GET  /health/live
GET  /health/ready
GET  /api/v1/version
```

필수 request headers:

```text
Authorization: Bearer <device-api-key>
Content-Type: application/json
X-Request-ID: <uuid>
Idempotency-Key: <stable-key>
X-Tonevyra-Schema-Version: t032.planner.request.v1
```

필수 response fields:

```text
schema_version
request_id
server_request_id
planner_version
policy_version
input_digest
plan
plan_digest
status
```

## 6. 데이터 최소화 정책

Allowed examples:

```text
scene classification
normalized subject/environment evidence
exposure/color/noise/sharpness measurements
image width/height/orientation
ISO, shutter, aperture, focal length when required
style/profile identifier without customer identity
quality retry summary without local paths
```

Forbidden examples:

```text
original_image
preview_image
image_bytes
base64_image
filename
absolute_path
relative_path
input_folder
output_folder
GPS / geolocation
camera_serial_number
user_name / customer_name / email
raw_prompt
raw_model_response
Lightroom catalog path
arbitrary command / plugin path / preset path
```

## 7. 로컬 상태와 재시도

기존 canonical `image_tasks.status`를 유지한다. `WAITING_FOR_API` 같은 새 top-level status를 추가하지 않는다.

```text
ANALYSIS_DONE
→ planner request artifact persisted
→ request event PLANNER_API_REQUESTED
→ success: CORRECTION_PLANNED
→ transient failure: remain ANALYSIS_DONE + PLANNER_API_RETRY_SCHEDULED event
→ retry budget exhausted: FAILED + PLANNER_API_RETRY_EXHAUSTED
```

기본 정책:

```text
connect_timeout_seconds = 3
read_timeout_seconds = 12
total_attempts = 3
backoff_seconds = 1, 2, 4 (+ bounded jitter)
max_retry_after_seconds = 30
client_concurrency = 1
max_request_body_bytes = 262144
```

Retryable:

```text
network unavailable
timeout
HTTP 408, 429, 500, 502, 503, 504
```

Not retryable without operator/config change:

```text
HTTP 400, 401, 403, 404, 409, 413, 422
schema incompatibility
response digest mismatch
unsupported planner/policy version
```

## 8. 서버 보안

```text
- Production HTTPS only
- device/customer-scoped API key
- server stores only salted/hashed key material where practical
- secret redaction in logs
- request body limit
- per-key rate limit
- endpoint allowlist
- CORS disabled unless a browser client is explicitly introduced
- Swagger/OpenAPI disabled or protected in production
- no runtime code download
- no arbitrary file or command input
- run as non-root system user
```

API key는 client source code에 평문 상수로 넣지 않는다. OS credential storage 또는 보호된 per-user configuration을 사용한다.

## 9. 서버 배포 경계

테스트 서버 권장값:

```text
Uvicorn workers = 1
Planner execution concurrency = 1
Nginx reverse proxy = enabled
TLS = enabled
systemd restart = on-failure with bounded restart window
request access log = metadata only
log rotation = enabled
```

Redis, Celery, NATS, MinIO, Kubernetes, worker pool은 T-032 범위가 아니다.

## 10. 오류 코드

```text
PLANNER_API_UNAVAILABLE
PLANNER_API_TIMEOUT
PLANNER_API_AUTH_FAILED
PLANNER_API_FORBIDDEN
PLANNER_API_RATE_LIMITED
PLANNER_API_SCHEMA_MISMATCH
PLANNER_API_RESPONSE_INVALID
PLANNER_API_RESPONSE_DIGEST_MISMATCH
PLANNER_API_VERSION_UNSUPPORTED
PLANNER_API_RETRY_EXHAUSTED
PLANNER_REQUEST_PRIVACY_VIOLATION
PLANNER_REQUEST_TOO_LARGE
IDEMPOTENCY_CONFLICT
PLANNER_SERVICE_NOT_READY
PLANNER_EXECUTION_FAILED
```

## 11. 구현 단계

```text
T-032-01 current Planner call boundary and payload inventory
T-032-02 canonical request/response/error schemas
T-032-03 Planner engine extraction into server package
T-032-04 FastAPI service endpoints and auth
T-032-05 local PlannerApiClient and durable request/response artifacts
T-032-06 bounded retry, idempotency, recovery, version validation
T-032-07 deployment configuration for Oracle test server
T-032-08 static/reference/live/soak verification
T-032-09 removal proof for Planner rules from production client build
```

## 12. 제외 범위

```text
- Qwen/vision model server migration
- original photo upload
- browser dashboard
- SaaS account/billing implementation
- multi-region failover
- Redis/Celery queue
- Kubernetes
- local production Planner fallback
- arbitrary batch endpoint
- asynchronous webhook completion
- auto update / licensing / obfuscation
- model training or fine-tuning
```

## 13. 하드 게이트

```text
GATE-01 production client build contains no Planner rule implementation
GATE-02 request capture contains no image bytes, paths, GPS, serial, prompt, or raw response
GATE-03 unauthorized request returns 401/403 without Planner execution
GATE-04 valid request returns schema-valid bounded CorrectionPlan
GATE-05 response request_id/input_digest match the persisted local request
GATE-06 same idempotency key + same digest replays same plan digest
GATE-07 same idempotency key + different digest returns 409
GATE-08 schema/version mismatch cannot reach Lightroom
GATE-09 transient outage uses bounded retry and durable resume
GATE-10 retry exhaustion produces explicit evidence, not silent local fallback
GATE-11 server restart leaves no duplicate Lightroom effect
GATE-12 HTTPS and secret-redacted logging verified
GATE-13 3000 sequential requests complete with no missing/duplicate IDs
GATE-14 T-019 through T-031 regression suite passes
```

## 14. 완료 판정

정적 문서와 reference harness만 통과한 상태는 다음과 같다.

```text
READY_FOR_T032_IMPLEMENTATION
```

실제 client/server build와 HTTPS 서버 증거가 없으면:

```text
BLOCKED_T032_IMPLEMENTATION_EVIDENCE_MISSING
BLOCKED_T032_LIVE_SERVER_EVIDENCE_MISSING
BLOCKED_T032_CLIENT_BUILD_SCAN_MISSING
```

세 증거와 3000건 soak를 모두 통과한 경우에만 strict completion을 선언한다.
