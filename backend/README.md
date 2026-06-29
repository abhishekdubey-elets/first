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
officer-transfer news, extracts structured records with **OpenAI**, and serves
them (plus a RAG assistant) to the Next.js frontend on Vercel.

No Redis/Celery — the discovery cycle runs in-process and is triggered by a cron
(e.g. Supabase `pg_cron`) calling `POST /api/v1/agents/run-cycle`.

## Required Space secrets (Settings → Variables and secrets)

| Name | Value |
|------|-------|
| `OPENAI_API_KEY` | your OpenAI key |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:<pw>@<host>:5432/postgres` (Supabase) |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://postgres:<pw>@<host>:5432/postgres` (Supabase) |
| `DB_SSL` | `true` |
| `SECRET_KEY` | random (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `ENCRYPTION_KEY` | Fernet key (`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`) |
| `CRON_TOKEN` | random shared secret for the discovery cron |
| `BACKEND_CORS_ORIGINS` | your Vercel URL, e.g. `https://your-app.vercel.app` |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | dashboard login |

Health check: `/health` · API docs: `/docs`
