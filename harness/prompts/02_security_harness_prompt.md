# Prompt — Harden Model Security Checks

Read `AGENTS.md`, `skills/model-security/SKILL.md`, and `harness/scripts/run_security_check.py`.

Improve the security harness without changing project scope.

Required checks:

- `trust_remote_code=True` is prohibited.
- model loading must use local model path and `local_files_only=True`.
- no network calls from `src/mw_photo_agent/vision/`.
- no external URL image inputs.
- Qwen must remain a replaceable backend, not a hard dependency.
- online model download during processing is prohibited.

Do not connect or download any real model.
