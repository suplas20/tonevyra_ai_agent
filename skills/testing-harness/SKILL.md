# Testing Harness Skill

## Purpose
Provide deterministic validation scripts for each implementation ticket.

## Rules
- Harness tests must be repeatable.
- New work must be completed against the real local runtime path: local model backend plus Lightroom Classic plugin evidence.
- Mock and fake harnesses may remain as regression diagnostics, but they are not sufficient completion evidence for new work.
- Real model tests must remain local-only, offline, and network-blockable.
- Real Lightroom tests must validate durable apply/export evidence JSON and actual output files where export is in scope.
- Harness scripts should return non-zero on failure.
- Harness scripts must report what they checked.
