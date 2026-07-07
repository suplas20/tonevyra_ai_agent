# Planner API Contract Skill

## Purpose

Use this skill when defining or changing the T-032 request, response, error, digest, endpoint, or compatibility contract between the local Agent and the remote Planner Service.

## Rules

- `/api/v1` is the transport major boundary.
- Request, response, and error bodies have explicit schema versions.
- `request_id`, `input_digest`, `planner_version`, `policy_version`, and `plan_digest` are mandatory evidence.
- Request body and header request IDs must match.
- Canonical JSON serialization must be deterministic before digesting.
- Breaking semantics require a new schema/API major.
- The server may return only bounded CorrectionPlan data and metadata; never commands, arbitrary paths, plugin payloads, or executable instructions.
- The client validates the response independently before Lightroom.

## Privacy Contract

Use allowlisted request projection. Reject image bytes, filenames, paths, GPS, camera serial, prompt, raw model response, customer identity, and Lightroom catalog/preset paths.

## Idempotency Contract

Same principal + idempotency key + payload digest returns the committed response. A different digest with the same key returns `409 IDEMPOTENCY_CONFLICT`.

## Required Reading

```text
.docs/t032/T-032_API_Contract.md
harness/CONTRACT_T032_PLANNER_API_SEPARATION.md
harness/schemas/t032_planner_request.schema.json
harness/schemas/t032_planner_response.schema.json
harness/schemas/t032_planner_error.schema.json
```
