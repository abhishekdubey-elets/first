"""Create all tables from the ORM metadata (first-run convenience).

For production schema evolution use Alembic:
    alembic revision --autogenerate -m "msg" && alembic upgrade head

This script is idempotent (create_all skips existing tables) and is invoked by
the Docker entrypoint so the stack comes up working with one command.
"""
from __future__ import annotations

from app.core.database import ensure_schema


def main() -> None:
    # Uses the configured engine (honours DB_SSL for Supabase/Neon). Creates
    # missing tables AND adds columns introduced after the first deployment.
    ensure_schema()
    print("Database schema ensured.")


if __name__ == "__main__":
    main()
