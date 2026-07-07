# T-032 Planner API Separation Harness Contract

- T-031 baseline 47 skills remain and four T-032 skills are added; total 51.
- Local Qwen analysis remains on the user machine.
- Production Planner rules are absent from the local Agent distribution.
- Original/preview image data, filenames, paths, GPS, serial numbers, prompts, raw model responses, and customer identity do not cross the API boundary.
- The only accepted production Planner path is authenticated HTTPS `/api/v1/plans`.
- Client request evidence is durable before send.
- Request and plan canonical digests are verified at both boundaries.
- The client validates response schema, request ID, input digest, versions, plan digest, value ranges, and forbidden fields before Lightroom.
- Canonical image task statuses are unchanged; retries are represented through attempts/events while remaining at `ANALYSIS_DONE`.
- Retry, timeout, rate-limit waiting, and server restart behavior are bounded.
- Same idempotency key and digest replays the committed result; different digest conflicts.
- Production local Planner fallback is forbidden.
- Server authentication secrets and full private payloads are excluded from logs/artifacts.
- Reference harness evidence is not implementation or live HTTPS completion.
- Strict completion requires implementation runtime, live server, client build scan, and 3000 sequential soak evidence.
- T-019 through T-031 regressions remain mandatory.
