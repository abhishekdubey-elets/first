# syntax=docker/dockerfile:1
# Backend image for the IAS Transfer Intelligence API.
# Runs the FastAPI app only — no Celery/Redis (discovery runs in-process,
# triggered by a cron hitting /api/v1/agents/run-cycle). LLM is OpenAI (cloud).
# Suitable for Hugging Face Docker Spaces (listens on $PORT, default 7860).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=7860 \
    STORAGE_DIR=/app/data/storage \
    GOOGLE_CREDENTIALS_FILE=/app/data/secrets/google-credentials.json

WORKDIR /app

# All Python deps ship manylinux wheels (psycopg2-binary, asyncpg, lxml,
# Pillow, cryptography) so no compiler/system libs are needed. OCR binaries
# (tesseract/poppler) are intentionally omitted — OCR is off by default and
# isn't available on serverless hosts anyway.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Writable data dirs (ephemeral on Spaces; the DB is external/Supabase).
RUN mkdir -p /app/data/storage /app/data/secrets \
    && chmod -R 777 /app/data \
    && chmod +x /app/scripts/entrypoint.sh

EXPOSE 7860

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
# exec so SIGTERM reaches uvicorn (graceful shutdown of the scheduler).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
