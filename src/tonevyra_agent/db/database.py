"""SQLAlchemy engine, session, and database health helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tonevyra_agent.core.config import REQUIRED_DB_TABLES, REQUIRED_DB_VIEWS, Settings, get_settings


@dataclass(frozen=True)
class DatabaseIdentity:
    database_name: str
    user_name: str


@dataclass(frozen=True)
class RequiredObjectCheck:
    existing_tables: set[str]
    existing_views: set[str]
    missing_tables: tuple[str, ...]
    missing_views: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_tables and not self.missing_views


def create_db_engine(settings: Settings | None = None) -> Engine:
    config = settings or get_settings()
    return create_engine(config.database_url, pool_pre_ping=True, future=True)


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_db_engine(settings), expire_on_commit=False, future=True)


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    factory = create_session_factory(settings)
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_database_identity(engine: Engine) -> DatabaseIdentity:
    with engine.connect() as connection:
        row = connection.execute(text("select current_database(), current_user")).one()
    return DatabaseIdentity(database_name=row[0], user_name=row[1])


def check_required_objects(engine: Engine, settings: Settings | None = None) -> RequiredObjectCheck:
    config = settings or get_settings()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names(schema=config.database_schema))
    existing_views = set(inspector.get_view_names(schema=config.database_schema))
    missing_tables = tuple(table for table in REQUIRED_DB_TABLES if table not in existing_tables)
    missing_views = tuple(view for view in REQUIRED_DB_VIEWS if view not in existing_views)
    return RequiredObjectCheck(
        existing_tables=existing_tables,
        existing_views=existing_views,
        missing_tables=missing_tables,
        missing_views=missing_views,
    )
