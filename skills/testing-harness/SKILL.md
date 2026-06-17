# Testing Harness Skill

## Purpose
Provide deterministic validation scripts that prove each implementation ticket obeys the project skills, contract, and safety rules.

A harness is not just a fake environment. Mock Vision and Fake Lightroom are controlled substitutes used by the harness so the project can verify behavior before real Qwen or real Lightroom is connected.

## What the harness verifies
- The requested feature stays inside `project-scope`.
- Required artifacts are written before stages are marked complete.
- PostgreSQL task state, stage_results, task_events, and artifact rows agree.
- Autonomous loops are bounded and leave `loop_name` / `loop_iteration` evidence.
- Recovery uses DB + artifact evidence, not logs.
- Model execution stays local-only and offline.
- Real backend integration does not bypass mock/fake acceptance tests.

## Required Gate Order
```text
1. Static scope/security check
2. Unit or module harness
3. Mock Vision / Fake Lightroom harness
4. Smoke Pipeline
5. Recovery harness
6. Loop event verification
7. Real backend ticket, only when explicitly approved
```

## Rules
- Harness tests must be repeatable.
- Tests must avoid real Lightroom and real Qwen unless the current ticket explicitly requires them.
- Prefer seeded fixtures and fake backends.
- Harness scripts should return non-zero on failure.
- Harness scripts must report what they checked.
- A feature is not complete just because code was written; it is complete only when the relevant harness passes.
- Harness failures should be treated as implementation feedback, not as reasons to weaken the harness.

## Required Script Behavior
- Fail fast with a clear message.
- Print each passed check in human-readable form.
- Never silently skip a required check unless an explicit `--skip-*` flag was passed.
- Avoid network, external services, and customer images.
- Use synthetic or repository-safe fixtures only.

## Completion Criteria
A ticket may be marked complete only when:
```text
relevant skills were followed
required artifacts exist and verify checksum
DB state matches final status
loop evidence exists when the feature is autonomous
security harness passes when model/runtime code changed
smoke/recovery harness passes for pipeline changes
```
