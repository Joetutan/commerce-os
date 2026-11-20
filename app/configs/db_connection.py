from collections.abc import Generator
from functools import cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.configs.env_settings import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


@cache
def get_engine() -> Engine:
    """Return the cached engine for the configured database.

    `pool_pre_ping` discards connections that died while pooled.
    """
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the cached session factory bound to the shared engine.

    Sessions skip autoflush and keep attributes loaded after commit, so
    objects stay readable once the service layer has committed.
    """
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session]:
    """Yield a request-scoped session and always close it.

    Intended for `Depends(get_db)`; closing returns the connection to the
    pool even when the request fails.
    """
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
