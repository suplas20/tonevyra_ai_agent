# Planner API Service Skill

## Purpose

Use this skill to implement and operate the separate T-032 FastAPI Planner Service.

## Request Lifecycle

```text
size/content-type
→ auth/rate limit
→ schema/version
→ privacy/digest
→ idempotency
→ Planner engine
→ plan clamp/schema
→ response digest/commit
```

## Service Rules

- Planner rules live in the server package, not the production client package.
- The API layer does not duplicate Planner decision logic.
- Process liveness and readiness are separate endpoints.
- Readiness includes Planner policy and idempotency backend availability.
- Planner execution concurrency is bounded; reference 1 OCPU/1GB deployment uses 1.
- Stack traces are not returned to clients.
- Idempotency is durable for production retention; process memory alone is reference-only.
- Production service runs non-root behind HTTPS reverse proxy.
- Runtime code/model download is prohibited.
- CORS is disabled unless an explicit browser client is separately approved.

## Endpoints

```text
POST /api/v1/plans
GET /health/live
GET /health/ready
GET /api/v1/version
```

## Evidence

Record request correlation, principal/key hash prefixes, versions, latency, status, replay, and error code without secrets or full private payloads.
