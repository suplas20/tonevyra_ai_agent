# Installer Upgrade, Repair and Uninstall Skill

## Purpose

Use this skill for transactional upgrades, same-version repair, rollback and safe removal of Tonevyra-owned components.

## Mandatory Rules

- Stop Agent/Worker cleanly before replacement.
- Back up settings and DB migration metadata before upgrade.
- Replace application payload atomically where possible.
- Repair only Tonevyra-owned files and registrations.
- Preserve DB, photos, exports, settings and history by default.
- Require explicit confirmation for user-data deletion.
- Never remove system Python, Lightroom or user-managed PostgreSQL.
- PostgreSQL major upgrade requires a separate migration gate.
- Prove rollback and post-operation doctor results.
