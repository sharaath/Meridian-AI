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


def _sync_message_columns(target_engine) -> None:
    """Ensure message tree branching (parent_id) and feedback columns exist."""
    try:
        with target_engine.begin() as conn:
            if target_engine.dialect.name == "sqlite":
                res = conn.execute(text("PRAGMA table_info(messages);")).fetchall()
                col_names = {row[1] for row in res}
                if col_names:
                    if "parent_id" not in col_names:
                        conn.execute(text("ALTER TABLE messages ADD COLUMN parent_id VARCHAR(36);"))
                    if "feedback" not in col_names:
                        conn.execute(text("ALTER TABLE messages ADD COLUMN feedback VARCHAR(20);"))
            elif target_engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS parent_id VARCHAR(36);"))
                conn.execute(text("ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS feedback VARCHAR(20);"))
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").debug("Column sync note: %s", exc)


def init_db() -> None:
    """Create tables and ensure schema constraints support both Supabase and direct auth."""
    from app.models import tables  # noqa: F401
    try:
        Base.metadata.create_all(bind=engine)
        _sync_message_columns(engine)
        if get_settings().is_postgres:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_id_fkey;"))
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").warning("Database table verification deferred: %s", exc)


_fallback_engine = None
_fallback_sessionmaker = None


def _get_fallback_engine():
    global _fallback_engine, _fallback_sessionmaker
    if _fallback_engine is None:
        from app.config import BASE_DIR
        fallback_path = (BASE_DIR / "meridian_prod.db").as_posix()
        _fallback_engine = create_engine(
            f"sqlite:///{fallback_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=_fallback_engine)
        _sync_message_columns(_fallback_engine)
        _fallback_sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=_fallback_engine)
    return _fallback_sessionmaker


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session with automatic SQLite resilience."""
    try:
        db = SessionLocal()
        # Ping connection to verify database is reachable
        db.connection()
        yield db
    except Exception as exc:
        err_msg = str(exc).lower()
        if any(term in err_msg for term in ["tenant", "enotfound", "operationalerror", "connection to server"]):
            import logging
            logging.getLogger("uvicorn.error").warning(
                "Remote PostgreSQL unreachable (%s). Using automatic local SQLite fallback.", exc
            )
            fallback_session_factory = _get_fallback_engine()
            fallback_db = fallback_session_factory()
            try:
                yield fallback_db
            finally:
                fallback_db.close()
        else:
            raise
    finally:
        try:
            db.close()
        except Exception:
            pass

