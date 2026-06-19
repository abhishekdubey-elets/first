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

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# --- Async (API) -----------------------------------------------------------
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
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
    pool_size=5,
    max_overflow=10,
    echo=False,
)

sync_session_factory: sessionmaker[Session] = sessionmaker(
    bind=sync_engine, expire_on_commit=False
)


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
