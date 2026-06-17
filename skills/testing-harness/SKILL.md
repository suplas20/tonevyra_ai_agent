# Testing Harness Skill

## Purpose
Provide deterministic validation scripts for each implementation ticket.

## Rules
- Harness tests must be repeatable.
- Tests must avoid real Lightroom and real Qwen unless the current ticket explicitly requires them.
- Prefer seeded fixtures and fake backends.
- Harness scripts should return non-zero on failure.
- Harness scripts must report what they checked.
