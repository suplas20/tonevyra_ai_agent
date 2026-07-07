# T-032 구현 명세 — Planner Engine API Separation

## 1. 권장 저장소 구조

단일 저장소 안에서 패키지를 분리하거나, 보안·배포 정책에 따라 서버를 별도 private 저장소로 이동할 수 있다. 경계는 코드상 명확해야 한다.

```text
src/
├─ tonevyra_agent/
│  ├─ planner_api/
│  │  ├─ client.py
│  │  ├─ contracts.py
│  │  ├─ privacy.py
│  │  ├─ retry.py
│  │  └─ response_validator.py
│  └─ ... existing local pipeline
└─ tonevyra_planner_service/
   ├─ main.py
   ├─ api/
   │  ├─ plans.py
   │  ├─ health.py
   │  └─ version.py
   ├─ auth/
   ├─ contracts/
   ├─ planner/
   │  ├─ engine.py
   │  ├─ rules/
   │  └─ policies/
   ├─ idempotency/
   └─ observability/
```

Production client package/build must exclude `tonevyra_planner_service/planner/` and any legacy local Planner rules.

## 2. 필수 인터페이스

```python
class PlannerApiClient(Protocol):
    def create_plan(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        analysis: dict,
        image_context: dict,
        preferences: dict,
    ) -> dict: ...

class PlannerRequestSanitizer(Protocol):
    def sanitize(self, payload: dict) -> dict: ...
    def assert_no_forbidden_fields(self, payload: dict) -> None: ...

class PlannerEngine(Protocol):
    def create_plan(self, request: dict) -> dict: ...

class IdempotencyStore(Protocol):
    def get(self, principal_id: str, key: str): ...
    def reserve(self, principal_id: str, key: str, payload_digest: str): ...
    def commit(self, principal_id: str, key: str, response: dict): ...
```

## 3. 요청 생성

```text
VisionAnalysisResult
→ canonical JSON normalization
→ privacy allowlist projection
→ schema validation
→ canonical serialization (UTF-8, sorted keys, stable number handling)
→ SHA-256 input_digest
→ request artifact atomic write
→ DB artifact registration
→ HTTP send
```

요청에는 allowlist projection을 사용한다. blocklist만으로 보안을 구현하지 않는다.

## 4. Canonical digest

Digest 대상은 HTTP headers가 아니라 canonical request body다.

```text
input_digest = sha256(canonical_json(request_body_without_input_digest))
plan_digest  = sha256(canonical_json(plan))
```

Client는 전송 전 `input_digest`를 계산하고, server response의 `input_digest`가 일치하는지 확인한다.

## 5. 로컬 artifact

```text
planner_request.json
planner_response.json
correction_plan.json
planner_api_attempts.json
```

권장 artifact types:

```text
PLANNER_API_REQUEST
PLANNER_API_RESPONSE
CORRECTION_PLAN
PLANNER_API_ATTEMPT_LOG
```

민감하지 않더라도 Authorization header와 API key는 artifact에 기록하지 않는다.

## 6. DB/상태 처리

기존 상태를 유지한다.

```text
ANALYSIS_DONE
  planner request persisted
  PLANNER_API_REQUESTED event
  attempt record
  success response validated
  correction plan persisted
CORRECTION_PLANNED
```

재시도 중에는 `ANALYSIS_DONE`을 유지하고 attempt/event로 진행을 표현한다. 새 status는 금지한다.

## 7. HTTP client 정책

```text
- TLS certificate verification enabled
- redirect disabled by default
- exact host allowlist
- connect/read timeout separated
- max response body bounded
- JSON content type required
- retry classification by transport/status/error code
- Retry-After capped
- no proxy inheritance unless explicitly configured
- no image/path/raw prompt fields
- one in-flight Planner request per local processing worker
```

## 8. 인증

MVP reference:

```text
Authorization: Bearer <device-scoped-api-key>
```

Server auth result must produce a principal identifier independent from the raw key. Logs may include principal hash prefix, never the raw key.

Forbidden:

```text
API key in Git
API key in exception text
API key in request artifact
API key in CLI process arguments
API key in URL query string
```

## 9. Server request lifecycle

```text
request size gate
→ content type gate
→ auth
→ rate limit
→ header/schema version gate
→ request schema validation
→ privacy scan
→ canonical digest verification
→ idempotency lookup/reservation
→ Planner execution
→ plan schema/range validation
→ response digest
→ idempotency commit
→ response
```

Planner exception must map to a stable API error. Stack traces are server logs only and must not be returned to clients.

## 10. Idempotency behavior

```text
new key + valid digest
  → execute and commit response

existing key + same digest + completed
  → return stored response, replayed=true

existing key + different digest
  → HTTP 409 IDEMPOTENCY_CONFLICT

existing key + in-progress
  → bounded wait or HTTP 409/425 style explicit in-progress error
```

Production idempotency evidence must survive process restart for the configured retention period. Reference harness in-memory behavior is not sufficient for strict completion.

## 11. Versioning

```text
URL major: /api/v1
request schema: t032.planner.request.v1
response schema: t032.planner.response.v1
planner_version: semantic version of engine
policy_version: immutable rule/config version
```

Client compatibility allowlist must be explicit. Unknown major schema or unsupported planner/policy version is a hard rejection before Lightroom.

## 12. Plan validation

Client does not trust the server blindly.

```text
- response schema valid
- request_id exact match
- input_digest exact match
- plan_digest recomputed and matched
- known planner/policy versions
- all Lightroom values clamped to local contract
- no command/path/plugin payload fields
- no unknown local mask strategy
- requires_review respected
```

## 13. Health endpoints

`/health/live` proves process liveness only.

`/health/ready` proves:

```text
Planner engine loaded
required policy version available
idempotency store reachable
service accepting requests
```

`/api/v1/version` returns no secrets and includes supported schema versions.

## 14. Logging and metrics

Allowed fields:

```text
server_request_id
request_id
principal_id_hash_prefix
idempotency_key_hash_prefix
input_digest prefix
plan_digest prefix
planner/policy/schema version
status code
latency
retry/replay flag
error code
```

Forbidden log content:

```text
Authorization header
full API key
full analysis payload by default
photo/path/filename/GPS/serial
raw model response/prompt
full plan when not required for secure audit
```

## 15. Oracle 1 OCPU / 1GB reference deployment

```text
uvicorn workers=1
planner concurrency=1
no model runtime
no Redis/Celery
bounded access/error logs
systemd MemoryMax optional but monitored
Nginx TLS termination
swap is not a substitute for leak-free behavior
```

## 16. Test doubles

Allowed only in tests/harness:

```text
FakePlannerApiServer
MockPlannerApiClient
in-memory idempotency store
fixed deterministic Planner engine
```

They must be impossible to select silently in production configuration.

## 17. 금지 구현

```text
- original/preview image upload
- local production Planner fallback
- embedding Planner rules in client wheel/exe
- disable TLS verification
- follow arbitrary redirects
- unbounded retry
- retry all 4xx
- log secrets or full payloads
- trust arbitrary response fields
- server returning executable commands/paths
- browser CORS wildcard
- multiple Uvicorn workers with process-local idempotency only
```
