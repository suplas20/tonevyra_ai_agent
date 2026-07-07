# Planner API Security Skill

## Purpose

Use this skill for T-032 transport security, authentication, secret handling, data minimization, request/response integrity, abuse controls, and deployment hardening.

## Security Boundary

The Planner API is the only newly authorized remote runtime path. Qwen remains local. Photos and previews remain local.

## Mandatory Controls

```text
HTTPS certificate verification
exact server host allowlist
device/customer-scoped API key
secret redaction
request body limit
per-principal rate limit
schema and privacy validation
input/plan digests
bounded timeout/retry
non-root service
protected configuration
production docs endpoint disabled/protected
```

## Forbidden

```text
API key in source/Git/URL/CLI args
TLS verification disabled
wildcard redirect or host
image/path/GPS/serial/prompt/raw response upload
full payload/secret logging
server response containing executable command or arbitrary path
silent local Planner fallback
```

## Incident Conditions

Treat digest mismatch, idempotency conflict, forbidden field detection, repeated auth failure, abnormal request size, or unknown response version as explicit security/integrity incidents. Do not continue to Lightroom.
