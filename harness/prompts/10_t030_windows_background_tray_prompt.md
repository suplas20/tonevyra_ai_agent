# T-030 Harness Prompt

Verify that the implementation is a per-user Windows background Agent with a thin system-tray shell, a single Worker, stable-file gating, PostgreSQL-backed idempotent task registration, bounded supervision, graceful shutdown, and no source mutation.

Reject implementations that use Windows Service, SQLite queue/fallback, UI-owned business logic, processing before file stability, recursive output ingestion, unbounded restart, duplicate Workers, or screenshot-derived production icons.

Strict completion requires implementation runtime evidence and real Windows live evidence.
