#!/usr/bin/env bash
# Container entrypoint: ensure the schema exists, then exec the given command
# (uvicorn API, celery worker, or celery beat — set per service in compose).
set -euo pipefail

# Only the API container should bootstrap the DB schema. Other services wait.
if [[ "${RUN_DB_INIT:-0}" == "1" ]]; then
  echo "[entrypoint] Ensuring database schema..."
  python -m scripts.init_db || echo "[entrypoint] init_db failed (will retry on next boot)"
fi

exec "$@"
