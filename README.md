# IAS Transfer Intelligence Dashboard

An autonomous, multi-agent system that continuously monitors the internet for
**IAS (Indian Administrative Service) officer transfer news**, extracts
structured transfer records from articles and scanned government orders,
validates and de-duplicates them across sources, and syncs the verified records
to **Google Sheets** and an interactive **Next.js dashboard**.

The default language model is a **local, open-source LLM served by Ollama**, so
the whole pipeline runs offline with no API keys. OpenAI or Anthropic/Claude
can be plugged in optionally.

---

## Overview

Every 10 minutes a Celery beat tick wakes the discovery pipeline. News is pulled
from Google News and trusted RSS feeds (PIB, The Hindu, Indian Express, etc.),
relevant articles are fetched and (where needed) OCR'd, an LLM extracts a
structured transfer record, the record is validated and merged against existing
records, and verified records are pushed to Google Sheets. A FastAPI backend
exposes everything to the dashboard.

### The 7-agent architecture

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | **News Discovery** | Polls Google News + RSS feeds for IAS-transfer keywords, scores source trust, queues relevant articles. |
| 2 | **Article Extraction** | Fetches article HTML (respecting robots.txt), OCRs scanned PDFs/images of government orders via Tesseract + Poppler. |
| 3 | **Information Extraction** | Runs an LLM (Ollama by default) to pull a structured `IasTransfer` record from the article text. |
| 4 | **Validation** | Corroborates fields across sources, fills gaps, flags discrepancies, and raises/lowers confidence. |
| 5 | **Duplicate Detection** | Computes a stable dedup key (officer + gov-order-number, or officer + destination + date) to merge reports of the same transfer. |
| 6 | **Google Sheets** | Upserts each verified record into one row of the configured sheet (append new, overwrite updated). |
| 7 | **Dashboard** | Serves the FastAPI REST API + Next.js UI for exploring transfers, officers, news, logs, stats, and sync status. |

### Data flow

```
                        ┌──────────────────────────────────────────────┐
                        │       Celery Beat  (every 10 minutes)         │
                        │  app.workers.tasks.run_discovery_cycle        │
                        └───────────────────────┬──────────────────────┘
                                                │ enqueue
                                                ▼
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │ 1. News      │──▶│ 2. Article   │──▶│ 3. Info      │──▶│ 4. Validation│
   │   Discovery  │   │   Extraction │   │   Extraction │   │              │
   │ GoogleNews/  │   │ HTTP + OCR   │   │ LLM (Ollama) │   │ corroborate  │
   │ RSS feeds    │   │ (Tesseract)  │   │              │   │ flag conflict│
   └──────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘
                                                                   │
                                                                   ▼
                                                          ┌──────────────┐
                                                          │ 5. Duplicate │
                                                          │   Detection  │
                                                          │  dedup_key   │
                                                          └──────┬───────┘
                                                                 │ upsert
                            ┌────────────────────────────────────┼───────────────┐
                            ▼                                     ▼               ▼
                   ┌──────────────┐                    ┌──────────────┐  ┌──────────────┐
                   │  PostgreSQL  │◀───────────────────│ 6. Google    │  │ 7. Dashboard │
                   │ ias_transfers│                    │    Sheets    │  │ FastAPI +    │
                   └──────────────┘                    │   (gspread)  │  │ Next.js UI   │
                            ▲                           └──────────────┘  └──────────────┘
                            │  read/write
            FastAPI API  ◀──┘   Redis (Celery broker/result + cache)
```

---

## Tech stack

| Layer | Technology |
|-------|------------|
| API | FastAPI (uvicorn), Pydantic v2, JWT auth |
| Background jobs | Celery 5 + Redis (broker/result), Celery beat, Flower (monitoring) |
| Database | PostgreSQL 16, SQLAlchemy 2 (async asyncpg + sync psycopg2), Alembic |
| LLM | Ollama (default, local) · OpenAI · Anthropic/Claude — all via the OpenAI-compatible client |
| OCR | Tesseract (eng + hin) + Poppler for scanned government orders |
| Export | Google Sheets via `gspread` + a Google service account |
| Frontend | Next.js 14 (React, Tailwind) |
| Infra | Docker Compose |

---

## Prerequisites

- **Docker** and **Docker Compose** (the recommended path — everything is containerized).
- ~4 GB free disk for the Ollama model (`llama3.2:3b`).
- For local-without-docker dev: Python 3.12, Node.js 20, a running PostgreSQL 16 and Redis 7, plus `tesseract-ocr`, `tesseract-ocr-hin`, and `poppler-utils` for OCR.

---

## Quick start with Docker Compose

```bash
# 1. Configure environment
cp .env.example .env

# 2. Generate the two required secrets and paste them into .env:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# 3. Build and start the whole stack
docker compose up -d --build

# 4. Pull the local LLM model ONCE (required for extraction to work)
docker compose exec ollama ollama pull llama3.2:3b
```

The API container bootstraps the database schema automatically on first boot
(`RUN_DB_INIT=1` → `python -m scripts.init_db`).

### Default login

On startup the backend creates a first admin from your `.env`:

- **Email:** `FIRST_ADMIN_EMAIL` (default `admin@digitallearning.in`)
- **Password:** `FIRST_ADMIN_PASSWORD` (default `ChangeMe123!`)

Change these before any real deployment.

### URLs

| Service | URL |
|---------|-----|
| Dashboard (Next.js) | http://localhost:3000 |
| API + Swagger docs | http://localhost:8000/docs |
| API ReDoc | http://localhost:8000/redoc |
| Health check | http://localhost:8000/health |
| Flower (Celery monitor) | http://localhost:5555 |

### Optional: seed demo data

```bash
docker compose exec api python -m scripts.seed_demo
```

---

## Local development (without Docker)

```bash
# --- Backend -----------------------------------------------------------------
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Point .env (in repo root or backend/) at localhost services, e.g.:
#   DATABASE_URL=postgresql+asyncpg://ias:ias_password@localhost:5432/ias_transfers
#   REDIS_URL=redis://localhost:6379/0
#   OLLAMA_BASE_URL=http://localhost:11434/v1

python -m scripts.init_db                 # create tables
python -m scripts.seed_demo               # (optional) demo rows
uvicorn app.main:app --reload --port 8000

# In separate terminals:
celery -A app.workers.celery_app.celery worker --loglevel=info --concurrency=4
celery -A app.workers.celery_app.celery beat   --loglevel=info

# --- Frontend ----------------------------------------------------------------
cd frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

---

## Google Sheets export setup

The Sheets agent writes verified records into a Google Sheet using a **Google
service account**.

1. In Google Cloud Console, create a project and enable the **Google Sheets API**
   and **Google Drive API**.
2. Create a **service account** and download its JSON key.
3. Create a Google Sheet and **share it** with the service account's
   `client_email` (Editor access).
4. In the dashboard **Settings** page, upload the JSON key (it is stored at
   `GOOGLE_CREDENTIALS_FILE`, i.e. `/data/secrets/google-credentials.json`, on
   the shared `secrets` volume so api/worker/beat all see it) and set the
   spreadsheet ID + worksheet name.

The required OAuth scopes are `spreadsheets` and `drive.file`.

### Sheet column schema

Each transfer occupies exactly one row (new records append; updated records
overwrite in place). The header row is:

```
Timestamp | Officer Name | IAS Batch | Cadre | State | Previous District |
Previous Posting | New District | New Posting | Transfer Date | Effective Date |
Reason | Government Order Number | Government Order Link | Source Name |
Source URL | Confidence Score | Status | Last Updated
```

See [`docs/sample_google_sheet.csv`](docs/sample_google_sheet.csv) for the exact
header plus example rows. (A hidden trailing column stores the dedup key used to
locate a row for in-place updates.)

---

## Switching the LLM provider

The default is **Ollama** (local, open-source, offline) — no API key required.
Set `LLM_PROVIDER` in `.env`:

| Provider | `.env` |
|----------|--------|
| **Ollama** (default) | `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL=llama3.2:3b` |
| **OpenAI** (optional) | `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`, `OPENAI_MODEL=gpt-4.1-mini` |
| **Anthropic/Claude** (optional) | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...`, `ANTHROPIC_MODEL=claude-opus-4-8` |

All three providers go through the same OpenAI-compatible client. The provider
and model can also be overridden at runtime from the dashboard Settings page.

---

## Configuration reference

Every environment variable is documented in [`.env.example`](.env.example),
grouped by area, and maps 1:1 to `backend/app/core/config.py`. The two you
**must** set are `SECRET_KEY` and `ENCRYPTION_KEY`.

---

## API contract

See [`docs/API.md`](docs/API.md) for the full REST contract, or the live Swagger
docs at http://localhost:8000/docs.

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the production guide (reverse
proxy + TLS, scaling, backups, monitoring, and a security hardening checklist).


powershell -ExecutionPolicy Bypass -File .\start-all.ps1