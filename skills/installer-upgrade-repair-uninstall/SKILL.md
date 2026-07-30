# Installer Upgrade, Repair and Uninstall Skill

## Purpose

Use this skill for transactional upgrades, same-version repair, resumable partial installation, rollback and safe removal of Tonevyra-owned components.

## Mandatory Rules

- Stop Agent/Worker cleanly before replacement.
- Persist completed installer steps so a failed all-in-one install can resume safely.
- Back up settings and DB migration metadata before upgrade.
- Replace application payload atomically where possible.
- Repair only Tonevyra-owned files and registrations.
- Re-run Alembic only when the current revision is behind the application head.
- Never drop/recreate an existing database during normal repair.
- Preserve DB, photos, exports, settings and history by default.
- Require explicit confirmation for user-data deletion.
- Never remove system Python, Lightroom or user-managed PostgreSQL.
- Remove a Tonevyra-owned PostgreSQL service only under an explicit data-removal flow.
- PostgreSQL major upgrade requires a separate migration gate.
- Re-run the complete post-install doctor after upgrade/repair.
- Prove rollback, data preservation and idempotent re-entry.
