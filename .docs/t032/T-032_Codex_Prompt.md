# T-032 Codex 실행 프롬프트

다음 프롬프트를 Tonevyra AI Agent 저장소에서 실행한다.

```text
Read AGENTS.md first.
Then read CLAUDE.md.
Then read:
- .docs/t032/T-032_Planner_Engine_API_Separation_Work_Order.md
- .docs/t032/T-032_Implementation_Specification.md
- .docs/t032/T-032_API_Contract.md
- .docs/t032/T-032_Server_Deployment_Guide.md
- .docs/t032/T-032_Live_Test_Checklist.md
- .docs/09_Correction_Planner_Design_Agent.md
- .docs/13_Crash_Recovery_Error_Handling_Agent.md
- skills/planner-api-contract/SKILL.md
- skills/planner-api-client/SKILL.md
- skills/planner-api-service/SKILL.md
- skills/planner-api-security/SKILL.md
- skills/correction-planner/SKILL.md
- skills/resumable-idempotent-jobs/SKILL.md
- skills/production-reliability-operations/SKILL.md
- skills/testing-harness/SKILL.md
- harness/CONTRACT_T032_PLANNER_API_SEPARATION.md

Implement T-032 only.

Goal:
Extract the production Correction Planner engine from the local Agent and run it as an authenticated HTTPS JSON API service. Keep image detection, preview creation, local Qwen analysis, PostgreSQL task state, Lightroom execution, export, and quality evaluation on the client.

Mandatory boundaries:
1. Do not upload original photos or preview images.
2. Do not send local paths, filenames, GPS, camera serial, prompt, or raw model response.
3. Use an allowlist-based sanitized request projection.
4. Production client builds must not contain Planner rules or a selectable local Planner fallback.
5. The client must persist request/digest evidence before sending.
6. The server must validate auth, schema, privacy, input digest, idempotency, Planner output, and response digest.
7. The client must validate request_id, input_digest, schema/version, plan_digest, and adjustment bounds before Lightroom.
8. Keep existing image_tasks status values. Use events/attempt evidence during API retry.
9. Retries/timeouts/rate-limit waits must be bounded.
10. Same idempotency key + different payload digest must fail with 409.
11. Preserve all T-019 through T-031 behavior and tests.

Required endpoints:
- POST /api/v1/plans
- GET /health/live
- GET /health/ready
- GET /api/v1/version

Required implementation:
- PlannerApiClient interface and implementation
- request sanitizer and privacy guard
- canonical JSON and SHA-256 digest
- atomic request/response artifacts
- bounded retry classification
- FastAPI service with one Planner execution concurrency for reference deployment
- API key authentication with redacted logs
- durable idempotency implementation for production
- version compatibility checks
- health/readiness/version endpoints
- Nginx/systemd deployment files or templates
- client build scan proving Planner rule exclusion
- structured implementation/live/soak evidence

Do not implement:
- Qwen server migration
- image upload
- React dashboard
- Redis/Celery/NATS/Kubernetes
- browser wildcard CORS
- local production Planner fallback
- arbitrary batch or webhook API
- billing/licensing/obfuscation
- model training/fine-tuning

Validation order:
1. Inspect current Planner imports, artifacts, state transitions, and tests.
2. Run existing baseline tests before changing code.
3. Run static T-032 verifier.
4. Generate reference harness evidence.
5. Run implementation runtime evidence against the implemented service.
6. Run HTTPS live server probe.
7. Run client build scan.
8. Run 3000 sequential request soak.
9. Run T-019 through T-031 regressions.
10. Run strict T-032 verifier with all evidence.

Commands:
python harness/scripts/verify_t032_planner_api_separation.py --project-root .
python harness/scripts/run_t032_planner_api_reference.py --project-root .
python harness/scripts/run_t032_planner_api_live_probe.py --base-url https://<planner-host> --api-key-env TONEVYRA_PLANNER_API_KEY --output runtime/evidence/t032/t032_live_server_evidence.json

Hard stops:
- If a request needs image bytes or a local path, stop with BLOCKED_PLANNER_REQUEST_PRIVACY_VIOLATION.
- If production client packaging still includes Planner rules, stop with BLOCKED_T032_CLIENT_BUILD_SCAN_FAILED.
- If TLS verification must be disabled, stop with BLOCKED_T032_TLS_CONFIGURATION.
- If idempotency is process-local in a multi-worker production setup, stop with BLOCKED_T032_IDEMPOTENCY_NOT_DURABLE.
- If server/live testing is unavailable, report the exact BLOCKED state and do not claim strict completion.

Final report in Korean:
Ticket ID:
Implemented scope:
Client/server boundary:
Changed files:
Database/migration changes:
API contract/version:
Security/privacy evidence:
Idempotency evidence:
Retry/recovery evidence:
Client build scan:
3000-request soak:
Regression results:
Deployment files:
Blocked items:
Risks/follow-up:
Waiting for user approval:
```
