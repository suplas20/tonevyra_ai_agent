# Python MVP Structure Skill

## Purpose
Create a simple, CLI-first Python 3.11 project structure for Tonevyra AI.

## Rules
- Use package name `tonevyra_agent`.
- Keep business logic out of CLI handlers.
- Prefer clear modules over premature abstractions.
- Do not add FastAPI, React, Redis, Celery, MinIO, worker pools, or SaaS scope.
- Keep imports directional: CLI -> service/repository layers, not the reverse.

## Validation
- Package imports successfully.
- `python -m tonevyra_agent.cli doctor` runs.

## T-033 Bundled Runtime

Release packages must include exact Python 3.11.9 and locked dependencies. End-user installation must not require a separate Python installation, change PATH, or run public pip installs. Runtime diagnostics must prove that the executable uses only the bundled interpreter.
