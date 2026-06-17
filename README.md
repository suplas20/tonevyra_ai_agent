# MW Photo Agent

Local, CLI-first photo correction automation agent for Lightroom Classic.

The MVP processes photos end-to-end without a dashboard:

```text
runtime/input
-> file detection and stabilization
-> PostgreSQL task registration
-> 1024px sRGB JPEG preview
-> vision analysis
-> correction planning
-> Lightroom Classic JSON bridge
-> export
-> quality gate
-> PASS / REVIEW_REQUIRED / FAILED
```

## MVP Boundaries

- No external image, prompt, metadata, or model-response transmission.
- PostgreSQL stores operational state.
- Local artifacts store detailed payloads.
- Vision models analyze only; correction values are planned and clamped separately.
- Lightroom integration uses the Lua plugin plus file-based JSON bridge.
- React and FastAPI are deferred until the agent core works.

## Initial Commands

```bash
mw-agent init
mw-agent doctor
mw-agent start
mw-agent status
mw-agent scan
mw-agent retry TASK_ID
mw-agent test-lightroom
mw-agent test-vision
```

