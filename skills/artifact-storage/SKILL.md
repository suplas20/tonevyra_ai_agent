# Artifact Storage Skill

## Purpose
Persist task evidence as local files and register them in PostgreSQL.

## Atomic Write Rule
1. Write to a temp file in the same directory.
2. Flush/fsync when possible.
3. Atomic rename temp file to final path.
4. Calculate SHA-256 checksum and file size.
5. Register or update `task_artifacts`.
6. Only then mark the related stage complete.

## Required API
`save_json`, `save_text`, `save_bytes`, `load_json`, `load_text`, `exists`, `verify_checksum`.

## Do Not
- Do not mark a stage complete before artifacts are durable.
- Do not store image blobs in PostgreSQL.
- Do not use remote storage for MVP.
