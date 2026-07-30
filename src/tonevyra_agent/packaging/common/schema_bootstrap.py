"""Baseline schema bootstrap used by the T-033 installer.

This is an installer bootstrap bridge until Alembic migrations are added to the
repository. It creates the current ORM-backed MVP schema plus the required
summary view and alembic_version marker. It never drops existing objects.
"""

from __future__ import annotations

from sqlalchemy import text

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.db.database import create_db_engine
from tonevyra_agent.db.models import (
    FeedbackRecord,
    ImageTask,
    LearningSample,
    QualityResult,
    StageResult,
    TaskArtifact,
    TaskEvent,
)

BASELINE_REVISION = "t033_baseline"


def bootstrap_baseline_schema(settings: Settings | None = None) -> str:
    config = settings or get_settings()
    engine = create_db_engine(config)
    with engine.begin() as connection:
        connection.execute(text("create extension if not exists pgcrypto"))
    tables = [
        ImageTask.__table__,
        TaskArtifact.__table__,
        TaskEvent.__table__,
        StageResult.__table__,
        QualityResult.__table__,
        FeedbackRecord.__table__,
        LearningSample.__table__,
    ]
    for table in tables:
        table.create(engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table if not exists public.alembic_version (
                    version_num varchar(32) not null primary key
                )
                """
            )
        )
        connection.execute(
            text(
                """
                insert into public.alembic_version(version_num)
                values (:revision)
                on conflict (version_num) do nothing
                """
            ),
            {"revision": BASELINE_REVISION},
        )
        connection.execute(
            text(
                """
                create or replace view public.v_task_summary as
                select
                    t.id,
                    t.file_name,
                    t.file_ext,
                    t.status,
                    t.current_stage,
                    t.retry_count,
                    t.overall_score,
                    t.quality_decision,
                    t.error_code,
                    t.failed_stage,
                    t.created_at,
                    t.updated_at,
                    t.completed_at,
                    coalesce(a.artifact_count, 0)::bigint as artifact_count,
                    coalesce(e.event_count, 0)::bigint as event_count
                from public.image_tasks t
                left join (
                    select task_id, count(*)::bigint as artifact_count
                    from public.task_artifacts
                    group by task_id
                ) a on a.task_id = t.id
                left join (
                    select task_id, count(*)::bigint as event_count
                    from public.task_events
                    group by task_id
                ) e on e.task_id = t.id
                """
            )
        )
    return BASELINE_REVISION
