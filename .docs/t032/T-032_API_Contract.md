# T-032 Planner API 계약

## 1. Endpoint

```http
POST /api/v1/plans
```

### Required headers

```http
Authorization: Bearer <redacted>
Content-Type: application/json
X-Request-ID: 4a6c3f98-0be7-4dbe-bc72-24c065f40874
Idempotency-Key: task-01:attempt-01:8e2a...
X-Tonevyra-Schema-Version: t032.planner.request.v1
```

## 2. Request example

```json
{
  "schema_version": "t032.planner.request.v1",
  "request_id": "4a6c3f98-0be7-4dbe-bc72-24c065f40874",
  "client": {
    "agent_version": "0.32.0",
    "platform": "windows",
    "device_id_hash": "sha256:2f3a..."
  },
  "image_context": {
    "width": 6000,
    "height": 4000,
    "orientation": 1,
    "iso": 800,
    "shutter_seconds": 0.008,
    "aperture": 5.6,
    "focal_length_mm": 24.0
  },
  "analysis": {
    "analysis_schema_version": "vision.analysis.v1",
    "scene_type": "underwater",
    "environment": "ocean",
    "exposure_state": "severely_underexposed",
    "dominant_color_cast": "blue_green",
    "subject_type": "person",
    "subject_exposure": "dark",
    "highlight_clipping": 0.01,
    "shadow_clipping": 0.24,
    "confidence": 0.91
  },
  "preferences": {
    "correction_strength": "standard",
    "style_profile_id": "natural-v1"
  },
  "input_digest": "sha256:7a50..."
}
```

## 3. Success response

```json
{
  "schema_version": "t032.planner.response.v1",
  "status": "success",
  "request_id": "4a6c3f98-0be7-4dbe-bc72-24c065f40874",
  "server_request_id": "srv-01J...",
  "planner_version": "1.0.0",
  "policy_version": "2026-07-07.1",
  "input_digest": "sha256:7a50...",
  "replayed": false,
  "plan": {
    "global_adjustments": {
      "exposure": 1.25,
      "contrast": 8,
      "highlights": -20,
      "shadows": 35,
      "whites": 10,
      "blacks": -8,
      "temperature": 7100,
      "tint": 15,
      "texture": 5,
      "clarity": 4,
      "dehaze": 8,
      "vibrance": 12,
      "saturation": 0
    },
    "local_adjustments": [],
    "requires_review": false,
    "reason_summary": "bounded underwater exposure and color recovery"
  },
  "plan_digest": "sha256:398d..."
}
```

## 4. Error response

```json
{
  "schema_version": "t032.planner.error.v1",
  "status": "error",
  "request_id": "4a6c3f98-0be7-4dbe-bc72-24c065f40874",
  "server_request_id": "srv-01J...",
  "error": {
    "code": "PLANNER_API_SCHEMA_MISMATCH",
    "message": "request schema is not supported",
    "retryable": false,
    "retry_after_seconds": null
  }
}
```

## 5. HTTP mapping

| HTTP | Code | Client behavior |
|---:|---|---|
| 200 | success | validate digest/version/plan, persist, continue |
| 400 | invalid request | no automatic retry |
| 401 | auth failed | stop and surface configuration error |
| 403 | forbidden/inactive | stop and surface entitlement/device error |
| 409 | idempotency conflict | no retry; integrity incident |
| 413 | request too large | no retry; privacy/request construction defect |
| 422 | schema validation | no retry until code/data corrected |
| 429 | rate limited | bounded retry using capped Retry-After |
| 500/502/503/504 | service/transient | bounded retry |

## 6. Contract invariants

```text
- request_id in body and header must match
- input_digest must match canonical body
- response request_id and input_digest must match request
- client recomputes plan_digest
- unknown top-level fields may be rejected in strict mode
- no image bytes, filesystem paths, GPS, serial, prompt, raw model response
- no executable command, arbitrary plugin payload, preset path, or catalog path
- all adjustment fields remain within the existing CorrectionPlan contract
```

## 7. Compatibility

Backward-compatible additions may be introduced within `/api/v1` only when old clients can safely ignore them. Breaking field/type/semantic changes require a new schema major and, when necessary, `/api/v2`.
