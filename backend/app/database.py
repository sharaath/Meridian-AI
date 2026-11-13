"""SQLAlchemy database engine and session management supporting PostgreSQL (Supabase) and SQLite."""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _build_engine():
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create tables and ensure schema constraints support both Supabase and direct auth."""
    from app.models import tables  # noqa: F401
    try:
        Base.metadata.create_all(bind=engine)
        if get_settings().is_postgres:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_id_fkey;"))
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").warning("Database table verification deferred: %s", exc)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

