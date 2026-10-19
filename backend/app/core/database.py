"""Database engine + session management.

Two engines are exposed:

* ``async_engine`` / ``get_db`` — used by the FastAPI request lifecycle
  (asyncpg driver, fully async).
* ``sync_session_factory`` / ``session_scope`` — used by Celery workers and
  agents, which run synchronously (psycopg2 driver).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import AsyncGenerator, Iterator
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# Managed Postgres (Supabase/Neon) requires TLS. asyncpg takes ssl="require";
# psycopg2 takes sslmode="require".
_async_connect_args: dict = {"ssl": "require"} if settings.DB_SSL else {}
_sync_connect_args = {"sslmode": "require"} if settings.DB_SSL else {}

if settings.DB_TRANSACTION_POOLER:
    # Transaction-mode poolers multiplex sessions, so cached prepared statements
    # from one connection are unknown on the next; disable the cache and make
    # statement names unique per connection.
    _async_connect_args["statement_cache_size"] = 0
    _async_connect_args["prepared_statement_name_func"] = (
        lambda: f"__asyncpg_{uuid4()}__"
    )


def _pool_kwargs(pool_size: int, max_overflow: int) -> dict:
    if settings.DB_POOL_MODE.lower() == "null":
        return {"poolclass": NullPool}
    return {"pool_size": pool_size, "max_overflow": max_overflow}


# --- Async (API) -----------------------------------------------------------
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    connect_args=_async_connect_args,
    **_pool_kwargs(settings.DB_POOL_SIZE, settings.DB_MAX_OVERFLOW),
)

AsyncSessionFactory = async_sessionmaker(
    async_engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- Sync (Celery workers / agents) ----------------------------------------
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_pre_ping=True,
    echo=False,
    connect_args=_sync_connect_args,
    **_pool_kwargs(settings.DB_SYNC_POOL_SIZE, settings.DB_SYNC_MAX_OVERFLOW),
)

sync_session_factory: sessionmaker[Session] = sessionmaker(
    bind=sync_engine, expire_on_commit=False
)


# Columns added after the first deployment. ``create_all`` only creates missing
# TABLES, so new columns on existing tables are added here (idempotent) until a
# real Alembic migration chain exists. (table, column, DDL type/default)
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("articles", "resolved_url", "VARCHAR(2048)"),
    ("ias_transfers", "enrichment_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("ias_transfers", "source_headline", "VARCHAR(1024)"),
    ("ias_transfers", "last_enriched_at", "TIMESTAMP WITH TIME ZONE"),
)


def ensure_schema() -> None:
    """Create missing tables and add missing columns (idempotent, sync)."""
    import app.models  # noqa: F401 — register all tables on Base.metadata
    from sqlalchemy import inspect, text

    Base.metadata.create_all(sync_engine)
    with sync_engine.begin() as conn:
        insp = inspect(conn)
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}"))


def check_connection(timeout_seconds: float = 5.0) -> tuple[bool, str | None]:
    """Cheap liveness probe for /health. Returns (ok, error message)."""
    from sqlalchemy import text

    try:
        with sync_engine.connect().execution_options(
            timeout=timeout_seconds
        ) as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).splitlines()[0][:300]


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope for worker/agent code."""
    session = sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
