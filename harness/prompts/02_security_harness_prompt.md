# Prompt — Harden Model Security Checks

Read `AGENTS.md`, `skills/model-security/SKILL.md`, `skills/local-model-security/SKILL.md`, and `harness/scripts/run_security_check.py`.

Improve the security harness without changing project scope. The harness is an acceptance gate that checks skill compliance, not just a mock runtime.

Required checks:

- `trust_remote_code=True` is prohibited.
- model loading must use local model path and `local_files_only=True`.
- no network calls from `src/tonevyra_agent/vision/` or model worker code.
- no external URL image inputs.
- Qwen must remain a replaceable backend, not a hard dependency.
- online model download during processing is prohibited.
- benchmark or real backend tickets must not change the default backend automatically.
- commercial/default model candidates require license review evidence and benchmark evidence before promotion.

Do not connect or download any real model.
