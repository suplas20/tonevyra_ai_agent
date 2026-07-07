# Planner API Client Skill

## Purpose

Use this skill for the local Agent adapter that converts validated local analysis into a privacy-scrubbed Planner API request, persists evidence, performs bounded HTTPS calls, and validates responses.

## Client Pipeline

```text
analysis artifact
→ allowlist projection
→ privacy assertion
→ canonical digest
→ durable request artifact
→ bounded HTTPS request
→ response schema/version/digest/range validation
→ durable response + correction plan artifacts
→ existing Lightroom stage
```

## Mandatory Rules

- Original/preview images never enter the request.
- Persist request evidence before network send.
- Do not store Authorization headers or API keys in artifacts/logs.
- Verify TLS and exact host allowlist.
- Disable arbitrary redirects.
- Separate connect/read timeouts.
- Retry only classified transient failures and cap `Retry-After`.
- Keep the task at `ANALYSIS_DONE` while retrying; use events/attempt evidence.
- Never silently use a production local Planner fallback.
- Reject response request ID, digest, version, schema, range, or forbidden-field mismatch before Lightroom.
- Keep one in-flight Planner request per processing worker in T-032.

## Recovery

Restart reads the persisted request artifact and idempotency key. It must not regenerate a materially different request for the same attempt. A new payload requires a new attempt and idempotency key.

## Failure

Use explicit `PLANNER_API_*` error codes and bounded retry exhaustion. Authentication, schema, integrity, and idempotency conflict failures are not blind retry cases.
