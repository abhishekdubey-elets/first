# Deployment — Supabase + Hugging Face + Vercel (free tier)

Architecture (no Redis, no Celery):

```
Vercel (Next.js frontend) ──▶ Hugging Face Space (FastAPI) ──▶ Supabase (Postgres)
                                       ▲                              │
                       Supabase pg_cron pings /agents/run-cycle    OpenAI (LLM + embeddings)
                       every 10 min (discovery runs in-process)
```

Generate the secrets you'll reuse below:
```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('CRON_TOKEN=' + secrets.token_urlsafe(24))"
```

---

## 1) Supabase — the database

1. Create a project at supabase.com (free tier).
2. **Project Settings → Database → Connection string**. Take the host/password.
   Build two URLs (use the **Session** connection, port 5432):
   - `DATABASE_URL = postgresql+asyncpg://postgres:<PW>@<HOST>:5432/postgres`
   - `DATABASE_URL_SYNC = postgresql+psycopg2://postgres:<PW>@<HOST>:5432/postgres`
3. Set `DB_SSL=true` (Supabase requires TLS).

Tables are created automatically on the backend's first boot (`RUN_DB_INIT=1`).

---

## 2) Hugging Face — the backend (Docker Space)

1. Create a **Docker** Space (huggingface.co → New Space → SDK: Docker).
2. Push the **`backend/`** folder to the Space repo (it contains `Dockerfile` +
   `README.md` with the Space metadata):
   ```bash
   cd backend
   git init && git add . && git commit -m "deploy"
   git remote add space https://huggingface.co/spaces/<user>/<space>
   git push space main
   ```
   (or drag-drop the files in the Space's web "Files" tab.)
3. Space → **Settings → Variables and secrets**, add:
   `OPENAI_API_KEY`, `DATABASE_URL`, `DATABASE_URL_SYNC`, `DB_SSL=true`,
   `SECRET_KEY`, `ENCRYPTION_KEY`, `CRON_TOKEN`, `RUN_DB_INIT=1`,
   `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD`, and
   `BACKEND_CORS_ORIGINS=https://<your-vercel-app>.vercel.app`.
4. The Space builds and serves at `https://<user>-<space>.hf.space`.
   Check `https://<user>-<space>.hf.space/health` → `{"status":"ok"}`.

---

## 3) Vercel — the frontend

1. Push the repo to GitHub, then import it at vercel.com → New Project.
2. **Root Directory** = `first/frontend` (or `frontend` if the repo root is `first`).
3. **Environment Variable**:
   `NEXT_PUBLIC_API_BASE_URL = https://<user>-<space>.hf.space`
4. Deploy. Vercel auto-detects Next.js.
5. Back on Hugging Face, make sure `BACKEND_CORS_ORIGINS` is your final Vercel URL.

---

## 4) Schedule discovery — Supabase pg_cron (replaces Celery beat)

Supabase → **SQL Editor**, run once:
```sql
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule('ias-discover', '0 2 * * *', $$
  select net.http_post(
    url     := 'https://<user>-<space>.hf.space/api/v1/agents/run-cycle',
    headers := '{"x-cron-token": "<CRON_TOKEN>"}'::jsonb
  );
$$);
```
This fires once daily (02:00 UTC) (and keeps the free Space awake). Trigger one
immediately to test:
```bash
curl -X POST https://<user>-<space>.hf.space/api/v1/agents/run-cycle \
  -H "x-cron-token: <CRON_TOKEN>"
```

---

## Notes
- **Cost:** Supabase, Hugging Face, and Vercel free tiers cover this; only OpenAI
  usage is paid (cheap with `gpt-4.1-mini` + `text-embedding-3-small`).
- **Free Space sleeps** when idle; the pg_cron ping wakes it. For guaranteed
  always-on, upgrade the Space or use Render/Railway instead.
- **OCR** (scanned gov-order PDFs) is off — it needs Tesseract/Poppler binaries,
  which aren't on the slim image. Add them back to the Dockerfile + set
  `ENABLE_OCR=true` only if self-hosting.
