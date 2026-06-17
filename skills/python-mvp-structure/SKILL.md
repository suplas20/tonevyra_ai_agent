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
