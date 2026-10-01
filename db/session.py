from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def resolve_database_url(root: Path | None = None) -> str:
    """Return DATABASE_URL. Default: sqlite file under data/review.db."""
    explicit = (os.environ.get("DATABASE_URL") or "").strip()
    if explicit:
        return explicit
    base = root or ROOT
    db_path = (base / "data" / "review.db").resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Absolute path so cwd does not matter for SQLite.
    return f"sqlite:///{db_path}"


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine(*, url: str | None = None, echo: bool = False) -> Engine:
    global _engine, _SessionLocal
    resolved = url or resolve_database_url()
    if _engine is not None and url is None:
        return _engine
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    engine = create_engine(resolved, echo=echo, future=True, connect_args=connect_args)
    if resolved.startswith("sqlite"):
        _configure_sqlite(engine)
    if url is None:
        _engine = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_session_factory(*, url: str | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if url is not None:
        engine = get_engine(url=url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def reset_engine() -> None:
    """Drop cached engine (tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(*, url: str | None = None) -> Engine:
    """Create tables if missing (dev bootstrap). Prefer Alembic in production."""
    from db.models import Base

    engine = get_engine(url=url)
    Base.metadata.create_all(bind=engine)
    return engine


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
