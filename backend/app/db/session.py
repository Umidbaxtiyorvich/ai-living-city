"""
Database connection.

SQLite by default and PostgreSQL by configuration: the URL is the only thing
that changes, because the schema in `models.py` deliberately uses no
dialect-specific types. Running the simulator should not require installing a
database server first, but nothing here stops production from using one.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def _create_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        future=True,
        # The simulation loop and the request handlers share one connection
        # pool across threads; SQLite refuses that unless told otherwise.
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=not is_sqlite,
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _configure(connection, _record):  # pragma: no cover - driver hook
            cursor = connection.cursor()
            # WAL lets the autosave write while a request reads.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _create_engine(settings.database_url)
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=engine(), expire_on_commit=False, future=True)
    return _Session


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transaction that commits on success and rolls back on failure."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset(url: str | None = None) -> None:
    """
    Points the module at a different database. For tests and for the CLI.
    """
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = _create_engine(url) if url else None
    _Session = None
