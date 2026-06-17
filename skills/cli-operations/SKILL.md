# CLI Operations Skill

## Purpose
Expose MVP operations through CLI while keeping business logic outside CLI handlers.

## Required Commands
`init`, `doctor`, `start`, `stop`, `status`, `tasks`, `task`, `scan`, `retry`, `process`, `test-lightroom`, `test-vision`, `loop-events`.

## Rules
- CLI should call service/repository layers.
- Do not put core business logic inside CLI commands.
