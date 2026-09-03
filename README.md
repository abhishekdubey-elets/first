# IAS Transfer Intelligence Dashboard

An autonomous, multi-agent system that monitors the internet for **IAS (Indian
Administrative Service) officer transfer news**, extracts structured transfer
records from articles with an LLM, validates and de-duplicates them across
sources, and syncs verified records to **Google Sheets** and an interactive
**Next.js dashboard** (news feed, transfer explorer, analytics, and a RAG
assistant that answers questions over the collected records).

The whole pipeline runs inside a single FastAPI process: an in-process
scheduler (APScheduler) fires a discovery cycle every hour and once at boot.
No separate worker, message broker, or local LLM is needed — extraction uses
the OpenAI API (Anthropic is supported as an alternative provider).

---

## Architecture

### Agents (`backend/app/agents`)

| # | Agent | Module | Responsibility |
|---|-------|--------|----------------|
| 1 | **Discovery** | `discovery.py`, `sources.py` | Polls Google News RSS per keyword (English + Hindi) plus curated outlet RSS feeds (PIB, The Hindu, Indian Express, TOI, HT, LiveMint, NDTV). Applies a cheap headline relevance filter, resolves Google News redirect links to the publisher URL (`services/gnews.py`), and stores new `Article` rows as `discovered`. |
| 2 | **Extraction** | `extraction.py` | Fetches the article HTML (robots.txt respected) and extracts the body text. Optional OCR of scanned government-order PDFs/images when `ENABLE_OCR=true`. |
| 3 | **Information** | `information.py` | Calls the LLM with a strict JSON schema to extract zero or more `IasTransfer` records (officer, batch, cadre, state, from/to posting, dates, order number, ...). Validates Indian state names. |
| 4 | **Dedupe / Validation** | `dedupe.py` | Computes a stable dedup key (officer + order number, or officer + destination + date), merges reports of the same transfer, records corroborating sources and flags conflicting fields. |
| 5 | **Enrichment** | `enrichment.py` | Web-searches to fill missing from/to/state/date on incomplete records; at most `ENRICHMENT_MAX_ATTEMPTS` attempts per record, `ENRICHMENT_BATCH_SIZE` records per cycle. |
| 6 | **Google Sheets** | `sheets_agent.py`, `services/google_sheets.py` | Upserts each **verified** record into one row of the configured sheet (append new, overwrite updated). |
| — | **Orchestrator** | `orchestrator.py`, `workers/tasks.py` | Wires the agents into one cycle, processes pending articles newest-first within a time budget, sends notifications for new records, and purges news older than `NEWS_RETENTION_DAYS` (transfer records are kept). |

### Data flow

```
   Triggers (only ONE cycle runs at a time; others report "skipped"):
     - APScheduler inside the API process: every DISCOVERY_INTERVAL_SECONDS (default 1h) + once at boot
     - POST /api/v1/agents/run-cycle  (header x-cron-token: <CRON_TOKEN>, e.g. from Supabase pg_cron)
     - Dashboard admin button "Crawl now"  (POST /api/v1/agents/run)
                                   |
                                   v
 +-----------+   +------------+   +-------------+   +-----------------+   +------------+
 | Discovery |-->| Extraction |-->| Information |-->| Dedupe/Validate |-->| Enrichment |
 | GNews RSS |   | HTTP fetch |   | LLM -> JSON |   | dedup_key,      |   | web search |
 | + outlets |   | (+OCR opt) |   | schema      |   | corroborate     |   | fill gaps  |
 +-----------+   +------------+   +-------------+   +-----------------+   +-----+------+
                                                                                |
                    +-------------------+-------------------------+-------------+
                    v                   v                         v
           +----------------+   +----------------+       +------------------+
           |  PostgreSQL    |   | Google Sheets  |       |  Notifications   |
           |  (Supabase)    |   | VERIFIED only  |       | Slack/webhook/   |
           +-------+--------+   +----------------+       | email (optional) |
                   |                                     +------------------+
                   v
           +----------------+        +----------------------+
           |  FastAPI  API  | <----> |  Next.js dashboard   |
           |  /api/v1/*     |        |  (Vercel)            |
           +----------------+        +----------------------+

   Each cycle also purges articles older than NEWS_RETENTION_DAYS (default 15);
   their extracted transfer records are detached and kept.
```

### Frontend pages (`frontend/app`)

| Route | Purpose |
|-------|---------|
| `/` | Landing page |
| `/login` | Sign in (`FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD`) |
| `/dashboard` | Latest IAS transfer news at the top, pipeline status card (last/next run, running, errors), recent transfers, chart |
| `/news` | Searchable news feed, latest first, grouped by day |
| `/transfers` | Transfer explorer with filters and sorting |
| `/analytics` | Charts by state, cadre, district, month |
| `/assistant` | RAG chat over the transfer records |
| `/sync` | Google Sheets sync status, logs, retry |
| `/settings` | Sheet/worksheet, auto-export, OpenAI key, credentials upload |
| `/officers/[name]` | Officer transfer timeline |

---

## Tech stack

| Layer | Technology |
|-------|------------|
| API | FastAPI (uvicorn), Python 3.12, Pydantic v2, JWT auth |
| Scheduling | APScheduler `BackgroundScheduler` inside the API process (`ENABLE_INPROCESS_SCHEDULER`), plus a token-protected cron endpoint |
| Database | PostgreSQL 16 (Supabase in production), SQLAlchemy 2 — asyncpg for the API, psycopg2 for the pipeline |
| LLM | OpenAI (default, `gpt-4.1-mini`) via the OpenAI SDK, or Anthropic/Claude (`claude-opus-5`) via the official Anthropic SDK |
| RAG assistant | OpenAI embeddings (`text-embedding-3-small`) + chat model, optional web fallback |
| Discovery | feedparser (Google News RSS + outlet feeds), httpx, BeautifulSoup/lxml |
| OCR (optional) | Tesseract + Poppler, off by default |
| Export | Google Sheets via `gspread` + a Google service account |
| Frontend | Next.js 14, React 18, Tailwind, TanStack Query, Recharts |
| Hosting | Hugging Face Docker Space (backend), Vercel (frontend), Supabase (Postgres) |

---

## Production deployment topology

| Component | Where | Notes |
|-----------|-------|-------|
| Backend | Hugging Face Docker Space `abhishek-elets/ias-transfer-intelligence` | Built from `backend/Dockerfile`, listens on port 7860. URL: `https://abhishek-elets-ias-transfer-intelligence.hf.space` |
| Frontend | Vercel project `frontend` | Deployed with the Vercel CLI from `./frontend`; `NEXT_PUBLIC_API_BASE_URL` points at the Space URL |
| Database | Supabase Postgres | Connect through the **Session Pooler** host, with `DB_SSL=true` |

### Space secrets (Settings → Variables and secrets)

| Name | Value |
|------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres.<project-ref>:<pw>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres` |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://postgres.<project-ref>:<pw>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres` |
| `DB_SSL` | `true` |
| `OPENAI_API_KEY` | OpenAI key (`LLM_PROVIDER=openai` is the default) |
| `SECRET_KEY` | random string for JWT signing |
| `ENCRYPTION_KEY` | Fernet key for encrypting API keys stored at rest |
| `CRON_TOKEN` | shared secret for `POST /api/v1/agents/run-cycle` |
| `BACKEND_CORS_ORIGINS` | the Vercel URL(s), comma-separated |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | dashboard login |
| `GOOGLE_CREDENTIALS_JSON` | full service-account JSON (Space storage is ephemeral; this is written to disk at boot) |
| `GOOGLE_SHEET_ID` (variable) | target spreadsheet id |
| `DISCOVERY_INTERVAL_SECONDS` (variable) | cycle cadence, default `3600` |

**Supabase gotcha:** the direct host `db.<ref>.supabase.co` is IPv6-only and is
unreachable from the Space. Always use the Session Pooler host
(`aws-1-<region>.pooler.supabase.com:5432`) with the pooler username
`postgres.<project-ref>`. Both `DATABASE_URL` (asyncpg) and `DATABASE_URL_SYNC`
(psycopg2) must be set — the API uses the first, the pipeline the second.

Full deployment/redeploy steps are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Local development

### Quick start with Docker Compose

```bash
cp .env.example .env
# Generate the two required secrets and paste them into .env:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# Set OPENAI_API_KEY in .env (or later from the dashboard Settings page).

docker compose up -d --build
```

The API container ensures the schema on boot (`RUN_DB_INIT=1` runs
`python -m scripts.init_db`: `create_all` plus idempotent `ALTER TABLE ... ADD
COLUMN` for columns introduced later). The first discovery cycle starts a few
seconds after boot.

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API + Swagger docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

Optional demo rows: `docker compose exec api python -m scripts.seed_demo`.

### Without Docker

Requires Python 3.12, Node.js 20 and a running PostgreSQL 16.

```bash
# --- Backend -----------------------------------------------------------------
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# .env (repo root or backend/) should point at your local Postgres:
#   DATABASE_URL=postgresql+asyncpg://ias:ias_password@localhost:5432/ias_transfers
#   DATABASE_URL_SYNC=postgresql+psycopg2://ias:ias_password@localhost:5432/ias_transfers
python -m scripts.init_db
uvicorn app.main:app --reload --port 8000

# --- Frontend ----------------------------------------------------------------
cd frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

On Windows, `powershell -ExecutionPolicy Bypass -File .\start-all.ps1` starts
the backend (port 8000) and frontend (port 3001) in their own windows;
`stop-all.ps1` stops them.

### Default login

The backend creates a first admin on startup from `FIRST_ADMIN_EMAIL` (default
`admin@digitallearning.in`) and `FIRST_ADMIN_PASSWORD` (default `ChangeMe123!`).
Change both before any real deployment.

---

## Google Sheets export setup

The Sheets agent writes verified records into a Google Sheet using a **Google
service account**.

1. In Google Cloud Console, create a project and enable the **Google Sheets API**
   and **Google Drive API**.
2. Create a **service account** and download its JSON key.
3. Create a Google Sheet and **share it** with the service account's
   `client_email` (Editor access).
4. Provide the key to the backend, either:
   - upload it on the dashboard **Settings** page (stored at
     `GOOGLE_CREDENTIALS_FILE`), or
   - on ephemeral hosts such as Hugging Face Spaces, set the whole JSON as the
     `GOOGLE_CREDENTIALS_JSON` secret — it is written to
     `GOOGLE_CREDENTIALS_FILE` at every boot, so it survives restarts.
5. Set the spreadsheet ID and worksheet name (`GOOGLE_SHEET_ID`,
   `GOOGLE_WORKSHEET_NAME`, or the Settings page).

The required OAuth scopes are `spreadsheets` and `drive.file`. Only records in
the `verified` state are exported; `/sync` shows status and lets an admin retry
failed rows.

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

Set `LLM_PROVIDER` in `.env` (or the Space secrets):

| Provider | Settings |
|----------|----------|
| **OpenAI** (default) | `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`, `OPENAI_MODEL=gpt-4.1-mini` |
| **Anthropic/Claude** | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...`, `ANTHROPIC_MODEL=claude-opus-5` (optional `ANTHROPIC_EFFORT=medium`) |

Each provider uses its own official SDK. An OpenAI key can also be
set at runtime from the dashboard Settings page (stored Fernet-encrypted; doing
so switches the active provider to `openai`). The RAG assistant always uses
OpenAI embeddings (`EMBED_MODEL`).

---

## Configuration reference

Every environment variable is documented in [`.env.example`](.env.example),
grouped by section, and maps 1:1 to `backend/app/core/config.py`. The two you
**must** set are `SECRET_KEY` and `ENCRYPTION_KEY`; in practice you also need
`OPENAI_API_KEY` for extraction to work.

## API

See [`docs/API.md`](docs/API.md) for the REST contract, or the live Swagger UI
at `<backend>/docs`.

---

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| Space shows **RUNTIME_ERROR**, logs say `password authentication failed` | Fix the `DATABASE_URL` / `DATABASE_URL_SYNC` secrets: pooler host, `postgres.<project-ref>` username, correct password, `DB_SSL=true`. Restart the Space. |
| `/health` returns `status: degraded` | `database.error` holds the first line of the DB error; the process stays up so you can read it. Also check `startup.schema_ok` / `startup.admin_ok`. The direct `db.<ref>.supabase.co` host does not work from the Space (IPv6-only). |
| No articles / no transfers appearing | Log in and call `GET /api/v1/agents/status`: `last_error` shows why the last cycle failed, `next_run` when the next one fires, `running` whether one is in flight. Most often `OPENAI_API_KEY` is missing/invalid (`GET /api/v1/settings/models` shows which providers are available). Trigger a run with the dashboard "Crawl now" button or `POST /api/v1/agents/run`. |
| Cron endpoint returns 401 | `CRON_TOKEN` is empty or the `x-cron-token` header does not match. |
| Sheets export fails | `GET /api/v1/sync/status` → `sheet.error`. Ensure the sheet is shared with the service-account `client_email` and that the credentials file exists (`GOOGLE_CREDENTIALS_JSON` on Spaces). |
| Browser shows CORS errors | Add the exact frontend origin to `BACKEND_CORS_ORIGINS`. |
