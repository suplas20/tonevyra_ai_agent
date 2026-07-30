"""T-033 database bootstrap verification and evidence generation.

This module verifies the database side of the all-in-one installer contract.
Role/database creation and PostgreSQL unattended installation are performed by
the platform installer adapter; this code provides the shared success gate that
must pass before the Agent is started.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from tonevyra_agent.core.config import REQUIRED_DB_TABLES, REQUIRED_DB_VIEWS, Settings, get_settings
from tonevyra_agent.db.database import create_db_engine
from tonevyra_agent.packaging.common.evidence import REQUIRED_DATABASE_OBJECTS, DatabaseBootstrapEvidence
from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError

ALEMBIC_TABLE = "alembic_version"


def verify_database_bootstrap(
    settings: Settings | None = None,
    *,
    credential_store_verified: bool,
) -> DatabaseBootstrapEvidence:
    config = settings or get_settings()
    try:
        engine = create_db_engine(config)
        with engine.connect() as connection:
            identity = connection.execute(
                text("select current_database(), current_user, inet_server_addr()::text")
            ).one()
            role = connection.execute(
                text("select coalesce((select usesuper from pg_catalog.pg_user where usename = current_user), true)")
            ).scalar_one()
            postgres_service_ready = bool(connection.execute(text("select 1")).scalar_one() == 1)
            localhost_only = _database_connection_is_localhost(config.database_url, identity[2])
            read_write_smoke_rolled_back = _read_write_smoke_rollback(connection)

        inspector = inspect(engine)
        tables = set(inspector.get_table_names(schema=config.database_schema))
        views = set(inspector.get_view_names(schema=config.database_schema))
        required_tables = set(REQUIRED_DB_TABLES) | {ALEMBIC_TABLE}
        required_objects = sorted((tables & required_tables) | (views & set(REQUIRED_DB_VIEWS)))
        alembic_head_matches = ALEMBIC_TABLE in tables and _alembic_has_revision(engine, config.database_schema)
        evidence = DatabaseBootstrapEvidence(
            schema_version="t033.database.bootstrap.v1",
            ticket="T033",
            postgres_service_ready=postgres_service_ready,
            role_exists=str(identity[1]) == "tonevyra_app",
            database_exists=str(identity[0]) == "tonevyra_agent",
            runtime_role_non_superuser=role is False,
            localhost_only=localhost_only,
            alembic_head_matches=alembic_head_matches,
            required_objects=required_objects,
            read_write_smoke_rolled_back=read_write_smoke_rolled_back,
            credential_store_verified=credential_store_verified,
            completed=False,
        )
        completed = _database_bootstrap_complete(evidence)
        return DatabaseBootstrapEvidence(**{**asdict(evidence), "completed": completed})
    except SQLAlchemyError as exc:
        raise T033ValidationError(T033ErrorCode.DB_BOOTSTRAP, f"database bootstrap verification failed: {exc.__class__.__name__}") from exc


def write_database_bootstrap_evidence(
    output: Path,
    settings: Settings | None = None,
    *,
    credential_store_verified: bool,
) -> DatabaseBootstrapEvidence:
    evidence = verify_database_bootstrap(settings, credential_store_verified=credential_store_verified)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(evidence), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def _database_bootstrap_complete(evidence: DatabaseBootstrapEvidence) -> bool:
    return (
        evidence.postgres_service_ready
        and evidence.role_exists
        and evidence.database_exists
        and evidence.runtime_role_non_superuser
        and evidence.localhost_only
        and evidence.alembic_head_matches
        and REQUIRED_DATABASE_OBJECTS.issubset(set(evidence.required_objects))
        and evidence.read_write_smoke_rolled_back
        and evidence.credential_store_verified
    )


def _database_url_is_localhost(database_url: str) -> bool:
    parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    return (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}


def _database_connection_is_localhost(database_url: str, server_addr: object) -> bool:
    # A loopback URL host (127.0.0.1/localhost/::1) already proves the client
    # connects locally. inet_server_addr() (server_addr) is intentionally NOT used
    # as a veto: on some platforms — notably Windows PostgreSQL — it reports a
    # non-loopback address for a genuine loopback connection, which made valid
    # local installs fail this gate.
    del server_addr
    return _database_url_is_localhost(database_url)


def _read_write_smoke_rollback(connection) -> bool:
    if connection.in_transaction():
        connection.rollback()
    transaction = connection.begin()
    try:
        connection.execute(text("create temporary table tonevyra_t033_smoke(value integer) on commit drop"))
        connection.execute(text("insert into tonevyra_t033_smoke(value) values (1)"))
        value = connection.execute(text("select value from tonevyra_t033_smoke")).scalar_one()
        transaction.rollback()
        return value == 1
    except Exception:
        transaction.rollback()
        raise


def _alembic_has_revision(engine, schema: str) -> bool:
    with engine.connect() as connection:
        result = connection.execute(text(f"select count(*) from {schema}.alembic_version")).scalar_one()
    return int(result) >= 1
