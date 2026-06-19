# Deployment Guide — IAS Transfer Intelligence Dashboard

Production deployment of the full stack (Postgres, Redis, Ollama, FastAPI API,
Celery worker + beat, Flower, Next.js frontend) using Docker Compose behind an
nginx reverse proxy with TLS.

---

## 1. Server prerequisites

- A Linux host (Ubuntu 22.04+ recommended) with **Docker Engine** and the
  **Docker Compose** plugin.
- Minimum **4 vCPU / 8 GB RAM / 40 GB disk**. The local LLM (`llama3.2:3b`) and
  OCR are CPU-bound; allocate more cores for higher article throughput. A GPU
  host materially speeds up Ollama if available.
- Open inbound ports **80** and **443** only (everything else stays internal).
- A domain name with DNS A records for the API and dashboard (e.g.
  `api.example.com` and `app.example.com`).

---

## 2. Generate secrets

Never ship the default `SECRET_KEY`/`ENCRYPTION_KEY`. On the server:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Paste both into `.env`. Also set strong values for `FIRST_ADMIN_PASSWORD` and
the Postgres password. Set `ENVIRONMENT=production` and restrict
`BACKEND_CORS_ORIGINS` to your real dashboard origin(s).

> **Important:** `ENCRYPTION_KEY` encrypts API keys stored at rest in the DB.
> If you rotate it, previously stored encrypted values can no longer be
> decrypted — re-enter them after rotation.

---

## 3. Configure a real Postgres

You can keep the bundled `db` service, but for production prefer a managed or
dedicated Postgres 16 instance with its own backups and monitoring. Point the
backend at it (note the two URLs — async + sync):

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@db-host:5432/ias_transfers
DATABASE_URL_SYNC=postgresql+psycopg2://USER:PASSWORD@db-host:5432/ias_transfers
```

Bootstrap the schema once (the API does this automatically when `RUN_DB_INIT=1`,
or run it manually):

```bash
docker compose exec api python -m scripts.init_db
```

If you use an external DB, remove the `db` service and its `depends_on` /
healthcheck references from `docker-compose.yml`.

---

## 4. Reverse proxy with TLS (nginx)

Terminate TLS at nginx and proxy to the internal containers. Obtain certs with
Let's Encrypt / certbot. In production, bind the `api`, `flower`, and `frontend`
container ports to `127.0.0.1` (or drop the `ports:` mappings entirely and put
them on an internal Docker network) so only nginx is publicly reachable.

```nginx
# /etc/nginx/sites-available/ias.conf

# --- API (api.example.com) ---------------------------------------------------
server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    client_max_body_size 10m;   # allow service-account JSON uploads

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

# --- Dashboard (app.example.com) ---------------------------------------------
server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

# --- HTTP -> HTTPS redirect ---------------------------------------------------
server {
    listen 80;
    server_name api.example.com app.example.com;
    return 301 https://$host$request_uri;
}
```

Set the dashboard's `NEXT_PUBLIC_API_BASE_URL=https://api.example.com` and add
that origin to `BACKEND_CORS_ORIGINS`.

> **Flower** exposes Celery internals — do not expose it publicly. Reach it via
> SSH tunnel (`ssh -L 5555:127.0.0.1:5555 host`) or put it behind nginx with
> HTTP basic auth on an internal-only vhost.

---

## 5. Scaling workers

Discovery and per-article processing are CPU-bound (LLM inference + OCR). Scale
horizontally:

```bash
# Run more worker replicas
docker compose up -d --scale worker=3
```

Tune `--concurrency` per worker to roughly the number of cores available to that
container. Keep **exactly one** `beat` instance — running multiple beats would
schedule duplicate discovery cycles.

---

## 6. Celery beat cadence

`celery beat` enqueues `app.workers.tasks.run_discovery_cycle` every
`DISCOVERY_INTERVAL_SECONDS` (default **600 s = 10 minutes**). Lower it for
fresher data (at higher load and outbound-request volume) or raise it to be
gentler on sources. Per-run caps: `DISCOVERY_MAX_ARTICLES_PER_RUN` and
`DISCOVERY_LOOKBACK_HOURS`. You can also trigger a cycle on demand via
`POST /api/v1/agents/discover` (admin).

---

## 7. Backups

- **Postgres** (the source of truth): nightly logical dumps and retain offsite.
  ```bash
  docker compose exec -T db pg_dump -U ias ias_transfers | gzip > backup-$(date +%F).sql.gz
  ```
- **Secrets volume**: back up the `secrets` volume (Google service-account JSON).
  Treat it as sensitive — store encrypted.
- **Redis**: ephemeral broker/result state; no backup needed (jobs re-run).
- **Google Sheet**: an external, human-readable mirror of verified records — a
  useful secondary record but not a substitute for DB backups.

Test restores periodically.

---

## 8. Health monitoring

- **API**: `GET /health` → `{"status": "ok", "version": ...}` (the API container
  already has a Docker `HEALTHCHECK`). Point your uptime monitor at it.
- **Celery**: Flower at `:5555` shows worker liveness, queue depth, and task
  success/failure rates. Alert on rising failure rate or growing queue backlog.
- **Logs**: structured logs from each service via `docker compose logs -f api worker beat`.
  The dashboard also exposes `GET /api/v1/logs` and a Sync status page
  (`GET /api/v1/sync/status`).
- **Resources**: watch CPU/RAM on the host — sustained saturation means you need
  more worker replicas or a longer discovery interval.

---

## 9. Security hardening checklist

- [ ] **Rotate `SECRET_KEY`** (JWT signing) from the default; rotating it
      invalidates existing tokens (forces re-login).
- [ ] **Rotate `ENCRYPTION_KEY`** (Fernet) from the default; re-enter stored API
      keys after rotation since old ciphertext becomes undecryptable.
- [ ] **Change `FIRST_ADMIN_PASSWORD`** and the Postgres password from defaults.
- [ ] **Restrict CORS**: set `BACKEND_CORS_ORIGINS` to your exact dashboard
      origin(s) — never `*` in production.
- [ ] **TLS everywhere**: serve API and dashboard only over HTTPS; redirect HTTP.
- [ ] **Do not expose** Postgres (5432), Redis (6379), Ollama (11434), or Flower
      (5555) publicly — bind to `127.0.0.1` / internal network only.
- [ ] **Run containers non-root** where possible and keep base images patched
      (`docker compose pull` + rebuild on a schedule).
- [ ] **Protect Flower** with basic auth or an SSH tunnel.
- [ ] **Rate limiting**: add request rate limiting at the nginx layer (e.g.
      `limit_req_zone`) in front of the API, especially `/api/v1/auth/login`, to
      blunt brute-force and abuse.
- [ ] **Secrets at rest**: keep `.env` and the `secrets` volume off version
      control (already in `.gitignore`) and restrict file permissions.
- [ ] **Least privilege** for the Google service account — share only the target
      sheet, not the whole Drive.
