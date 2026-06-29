#!/bin/sh
# Container entrypoint: ensure the DB schema exists, then exec the app.
# Portable POSIX sh (works on python:3.12-slim without bash).
set -e

if [ "${RUN_DB_INIT:-1}" = "1" ]; then
  echo "[entrypoint] Ensuring database schema..."
  python -m scripts.init_db || echo "[entrypoint] init_db failed (will retry next boot)"
fi

exec "$@"
