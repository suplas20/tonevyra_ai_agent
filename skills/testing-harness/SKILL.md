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

## T-029 Harness Requirement

T-029 needs static schema/fixture checks, deterministic native-detection fallback evidence, failure/idempotency/rollback tests, and a strict real-Lightroom evidence file. A fake runtime must never be presented as proof that Lightroom created a native mask.

Scope update, 2026-06-29: radial-gradient / radial-template fallback is excluded. Harnesses must fail if `radial_template` is presented as executable T-029 completion evidence.

## T-030 Windows live evidence rule

For T-030, static and reference fixture evidence is necessary but insufficient. Strict completion requires evidence from the implemented runtime and an actual Windows user session proving tray visibility, single instance, copy-in-progress blocking, deduplication, pause/resume, Worker crash recovery, source integrity, graceful shutdown, and zero orphan processes.

## T-031 cross-platform memory evidence

Require static contract tests, reference lifecycle tests, Windows process-VRAM evidence, and macOS arm64/MPS/FSEvents/Lightroom live evidence. Reference tests must never be reported as strict live completion.

## T-032 Harness Gates

Static tests must verify 51 cumulative skills, request privacy, schemas, docs, and production fallback prohibition. Runtime tests must cover digests, response binding, retry classification, replay/conflict, restart resume, and forbidden response fields. Strict completion additionally requires real HTTPS service evidence, production client build scan, and 3000 sequential requests.
