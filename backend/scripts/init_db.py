"""Create all tables from the ORM metadata (first-run convenience).

For production schema evolution use Alembic:
    alembic revision --autogenerate -m "msg" && alembic upgrade head

This script is idempotent (create_all skips existing tables) and is invoked by
the Docker entrypoint so the stack comes up working with one command.
"""
from __future__ import annotations

from sqlalchemy import create_engine

from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401 — register all tables on Base.metadata


def main() -> None:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Base.metadata.create_all(engine)
    print("✓ Database tables ensured.")


if __name__ == "__main__":
    main()
