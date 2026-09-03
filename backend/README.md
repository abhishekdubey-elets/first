---
title: IAS Transfer Intelligence API
emoji: 🏛️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# IAS Transfer Intelligence — Backend API

FastAPI backend for the IAS Transfer Intelligence Dashboard. Discovers IAS
officer-transfer news (Google News RSS + outlet feeds), extracts structured
records with **OpenAI** (Anthropic optional), de-duplicates and enriches them,
exports verified records to Google Sheets, and serves everything (plus a RAG
assistant) to the Next.js frontend on Vercel.

No Redis/Celery. The discovery cycle runs **in-process**: an APScheduler job
inside the API fires it every `DISCOVERY_INTERVAL_SECONDS` (default 3600) and
once shortly after boot (`ENABLE_INPROCESS_SCHEDULER=true` by default). It can
also be triggered by `POST /api/v1/agents/run-cycle` with an `x-cron-token`
header (e.g. from Supabase `pg_cron`) or by the dashboard's "Crawl now" button.
Only one cycle runs at a time.

The container listens on `$PORT` (default 7860) and runs
`python -m scripts.init_db` on boot (`RUN_DB_INIT=1`) to create/upgrade the
schema.

## Required Space secrets (Settings → Variables and secrets)

| Name | Value |
|------|-------|
| `OPENAI_API_KEY` | your OpenAI key |
| `DATABASE_URL` | `postgresql+asyncpg://postgres.<project-ref>:<pw>@aws-1-<region>.pooler.supabase.com:5432/postgres` (Supabase **Session Pooler** host — the direct `db.<ref>.supabase.co` host is IPv6-only and unreachable from the Space) |
| `DATABASE_URL_SYNC` | same as above with `postgresql+psycopg2://` |
| `DB_SSL` | `true` |
| `SECRET_KEY` | random (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `ENCRYPTION_KEY` | Fernet key (`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`) |
| `CRON_TOKEN` | random shared secret for `POST /api/v1/agents/run-cycle` |
| `BACKEND_CORS_ORIGINS` | your Vercel URL, e.g. `https://your-app.vercel.app` |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | dashboard login |
| `GOOGLE_CREDENTIALS_JSON` | full Google service-account JSON (Space storage is ephemeral; the JSON is written to `GOOGLE_CREDENTIALS_FILE` at every boot) |

## Optional Space variables

| Name | Value |
|------|-------|
| `GOOGLE_SHEET_ID` | target spreadsheet id (worksheet defaults to `Transfers`) |
| `DISCOVERY_INTERVAL_SECONDS` | cycle cadence in seconds, default `3600` |
| `LLM_PROVIDER` | `openai` (default) or `anthropic` (then set `ANTHROPIC_API_KEY`) |
| `ENABLE_INPROCESS_SCHEDULER` | set `false` only if an external cron drives `/agents/run-cycle` exclusively |

See the repo root `.env.example` for every setting.

## Health

`GET /health` returns

```json
{"status": "ok" | "degraded",
 "version": "...",
 "database": {"ok": true, "error": null},
 "startup": {"db_ok": true, "db_error": null, "schema_ok": true, "admin_ok": true,
             "scheduler": "running" | "disabled" | "unavailable", "started_at": "..."},
 "scheduler": {"enabled": true, "interval_seconds": 3600, "next_run": "..."}}
```

`status` is `ok` when the database answers and `degraded` otherwise. The
process stays up even when the database is unreachable, so a bad
`DATABASE_URL` shows up here (`database.error`) instead of a crash loop.

API docs: `/docs` · Full contract: `docs/API.md` in the repo.
