# T-027 SaaS Plan Routing, Usage and Cost Control Harness Contract

## Contract

- Every job receives an immutable versioned Plan Policy snapshot.
- Free/Lite use module providers without model initialization.
- Standard/Pro use model providers unless explicit controlled fallback is allowed.
- Free/Lite output quality is not intentionally reduced.
- Quota and usage reserve/commit/release are user-scoped and idempotent.
- Quality retries do not double-count photo units.
- Billing integration is outside scope; internal compute telemetry remains separate.
- Strict evidence includes quota boundaries, duplicate events, retries, and fallback accounting.
- T-019 through T-026 regressions remain mandatory.
