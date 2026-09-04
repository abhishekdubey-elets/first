# Deployment Guide — IAS Transfer Intelligence Dashboard

Production topology:

| Component | Host | Details |
|-----------|------|---------|
| Backend (FastAPI + in-process scheduler) | Hugging Face Docker Space `abhishek-elets/ias-transfer-intelligence` | Built from `backend/Dockerfile`, port 7860. URL `https://abhishek-elets-ias-transfer-intelligence.hf.space` |
| Frontend (Next.js 14) | Vercel project `frontend` | Deployed with the Vercel CLI from `./frontend` |
| Database (PostgreSQL) | Supabase | Reached through the Session Pooler |

There is no separate worker, broker, or cron host: the discovery cycle runs on
a background thread inside the API container.

---

## 1. Generate secrets

Never ship the default `SECRET_KEY` / `ENCRYPTION_KEY`:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python3 -c "import secrets; print('CRON_TOKEN=' + secrets.token_urlsafe(32))"
```

> `ENCRYPTION_KEY` encrypts the runtime OpenAI key stored by the Settings page.
> If you rotate it, re-enter that key afterwards.

---

## 2. Supabase (database)

1. Create a Supabase project and note the project ref and database password.
2. In **Project Settings → Database → Connection string**, pick the
   **Session Pooler** entry. It looks like
   `aws-1-ap-northeast-2.pooler.supabase.com:5432` with user
   `postgres.<project-ref>`.
3. Build both URLs (the API uses asyncpg, the pipeline uses psycopg2):

```env
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres
DATABASE_URL_SYNC=postgresql+psycopg2://postgres.<project-ref>:<password>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres
DB_SSL=true
```

**Do not** use the direct host `db.<project-ref>.supabase.co`: it resolves to
IPv6 only and is unreachable from Hugging Face Spaces (the Space ends in
`RUNTIME_ERROR` / `/health` reports `degraded`).

The schema is created and upgraded automatically at container boot
(`python -m scripts.init_db` — `create_all` plus idempotent `ALTER TABLE ...
ADD COLUMN` for new columns). No manual migration step is needed.

### Optional: external cron with pg_cron

The in-process scheduler already runs the cycle on `DISCOVERY_INTERVAL_SECONDS` (daily in production). If you also want an
external trigger (or you set `ENABLE_INPROCESS_SCHEDULER=false`), enable the
`pg_cron` and `pg_net` extensions in Supabase and schedule:

```sql
select cron.schedule('ias-discovery', '0 * * * *', $$
  select net.http_post(
    url     := 'https://abhishek-elets-ias-transfer-intelligence.hf.space/api/v1/agents/run-cycle',
    headers := '{"x-cron-token": "<CRON_TOKEN>"}'::jsonb
  );
$$);
```

Overlapping triggers are safe — only one cycle runs at a time.

---

## 3. Backend on Hugging Face Spaces

The Space is a **Docker** Space whose repo is the contents of `./backend`
(`backend/README.md` carries the YAML front matter HF reads: `sdk: docker`,
`app_port: 7860`).

### Secrets and variables (Space → Settings → Variables and secrets)

Secrets:

| Name | Value |
|------|-------|
| `DATABASE_URL` | asyncpg pooler URL from step 2 |
| `DATABASE_URL_SYNC` | psycopg2 pooler URL from step 2 |
| `DB_SSL` | `true` |
| `OPENAI_API_KEY` | OpenAI key |
| `SECRET_KEY` | from step 1 |
| `ENCRYPTION_KEY` | from step 1 |
| `CRON_TOKEN` | from step 1 |
| `BACKEND_CORS_ORIGINS` | `https://<your-vercel-app>.vercel.app` (comma-separate several) |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | dashboard login |
| `GOOGLE_CREDENTIALS_JSON` | the full service-account JSON, single line. Space disks are ephemeral, so a file uploaded via the Settings page is lost on restart; this secret is written to `GOOGLE_CREDENTIALS_FILE` at every boot |

Variables (non-secret):

| Name | Value |
|------|-------|
| `ENVIRONMENT` | `production` |
| `GOOGLE_SHEET_ID` | target spreadsheet id |
| `GOOGLE_WORKSHEET_NAME` | default `Transfers` |
| `DISCOVERY_INTERVAL_SECONDS` | `86400` in production (daily); code default `3600` |
| `LLM_PROVIDER` | `openai` (default) or `anthropic` |

### Deploy / redeploy

The Space builds from its own git repository, whose root is this repo's
`backend/` directory (the two histories are unrelated, so `git subtree push`
will not work). Use the helper script, which clones the Space repo, mirrors
`backend/` into it, commits and pushes:

```powershell
$env:HF_TOKEN = "<hugging-face token with write access>"
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_backend.ps1 -Message "fix: ..."
```

Doing it by hand is the same thing: clone
`https://huggingface.co/spaces/abhishek-elets/ias-transfer-intelligence`, copy
the contents of `backend/` over it (excluding `.git`), commit, push to `main`.
Every push rebuilds the image and restarts the container; secrets are kept.
Changing a secret in the Space settings also restarts it.

Verify:

```bash
curl https://abhishek-elets-ias-transfer-intelligence.hf.space/health
```

Expect `"status": "ok"`, `"startup": {"db_ok": true, "schema_ok": true,
"admin_ok": true, "scheduler": "running"}` and a `scheduler.next_run` timestamp.

---

## 4. Frontend on Vercel

```bash
cd frontend
npm i -g vercel            # once
vercel login               # once
vercel link                # once — link to the "frontend" project

# environment: production
vercel env add NEXT_PUBLIC_API_BASE_URL production
#   value: https://abhishek-elets-ias-transfer-intelligence.hf.space

vercel deploy --prod
```

`NEXT_PUBLIC_API_BASE_URL` is baked in at build time, so change it in the
Vercel project settings and redeploy if the backend URL changes. Add the
resulting Vercel URL (and any custom domain) to the Space's
`BACKEND_CORS_ORIGINS`.

---

## 5. Google Sheets

1. Create a service account with the Sheets + Drive APIs enabled, download the
   JSON key, and share the target sheet with its `client_email` (Editor).
2. Put the JSON into the `GOOGLE_CREDENTIALS_JSON` secret and set
   `GOOGLE_SHEET_ID`.
3. Check `/sync` in the dashboard (`GET /api/v1/sync/status` → `sheet.connected`).

Only `verified` records are exported; `POST /api/v1/sync/retry` re-runs failed
rows.

---

## 6. Backups

- **Supabase Postgres** is the source of truth. Supabase takes daily backups on
  paid plans; additionally take logical dumps with the pooler URL:
  ```bash
  pg_dump "postgresql://postgres.<project-ref>:<password>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require" \
    | gzip > backup-$(date +%F).sql.gz
  ```
- **Space secrets** (`GOOGLE_CREDENTIALS_JSON`, keys): keep a copy in a password
  manager — the Space filesystem is ephemeral and nothing on it needs backup.
- **Google Sheet**: a human-readable mirror of verified records, not a substitute
  for DB backups.
- News articles are purged after `NEWS_RETENTION_DAYS` (default 15) by design;
  transfer records are retained.

---

## 7. Monitoring

- `GET /health` — `status`, live DB probe, startup diagnostics, scheduler
  `next_run`. Point an uptime monitor at it.
- `GET /api/v1/agents/status` (JWT) — `last_run`, `last_error`, `running`,
  `next_run`; also shown on the dashboard's pipeline card.
- `GET /api/v1/sync/status` (JWT) — Sheets connectivity and failed exports.
- Space **Logs** tab — structured JSON logs (`discovery_cycle`,
  `discovery_cycle_failed`, `database_unreachable`, ...).
- Free Spaces sleep after inactivity; the scheduler only runs while the
  container is awake. Keep the Space "always on" (paid) or drive it with the
  pg_cron trigger above, which also wakes it.

---

## 8. Security checklist

- [ ] Change `FIRST_ADMIN_PASSWORD` (and `FIRST_ADMIN_EMAIL`) from the defaults.
- [ ] Set a random `SECRET_KEY` (JWT signing). Rotating it logs everyone out.
- [ ] Set a real Fernet `ENCRYPTION_KEY`; re-enter the runtime OpenAI key after rotation.
- [ ] Set a random `CRON_TOKEN`; with it empty, `/agents/run-cycle` always returns 401.
- [ ] Restrict `BACKEND_CORS_ORIGINS` to the exact Vercel/custom-domain origins — never `*`.
- [ ] Set `ENVIRONMENT=production`.
- [ ] Keep the Supabase database password and service-account JSON only in Space secrets / a password manager, never in git (`.env`, `*-credentials.json` are git-ignored).
- [ ] Share the Google Sheet with the service account only (least privilege), not the whole Drive.
- [ ] Use Supabase's network restrictions if your plan supports them; the Space has no fixed egress IP, so leave the pooler reachable but keep the password strong.

---

## Keeping the crawler alive

The crawler is an in-process scheduler inside the API container. A free
Hugging Face Space pauses after 48 hours without an HTTP request, and the
scheduler pauses with it, so a quiet weekend would silently skip crawls.

`.github/workflows/keepalive.yml` covers this from GitHub Actions:

| Job | Schedule | Does |
|---|---|---|
| `ping` | every 15 minutes | `GET /health`, so the Space never idles |
| `crawl` | 02:30 UTC daily (08:00 IST) | `POST /api/v1/agents/run-cycle` with the cron token, so the crawl runs even if the Space did pause |

One-time setup:

1. Merge to the default branch (scheduled workflows only run there).
2. Add the Space's `CRON_TOKEN` value as a repository secret named
   `CRON_TOKEN` under Settings → Secrets and variables → Actions. If you no
   longer have the value, set a new one in both places.
3. Optionally run the workflow once by hand from the Actions tab with
   "Also trigger a crawl now" ticked, to confirm the secret works.

GitHub disables scheduled workflows after 60 days with no commits; any commit
re-enables them. For belt and braces, also point a free uptime monitor
(UptimeRobot, cron-job.org) at `/health` every 15 minutes — it needs no
credentials and gives you downtime alerts as a bonus.
