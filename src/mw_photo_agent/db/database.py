"""Database engine and session helpers."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mw_photo_agent.core.config import Settings, get_settings


def create_db_engine(settings: Settings | None = None):
    config = settings or get_settings()
    return create_engine(config.database_url, pool_pre_ping=True)


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_db_engine(settings), expire_on_commit=False)


def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    factory = create_session_factory(settings)
    with factory() as session:
        yield session

