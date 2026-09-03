# API Contract — IAS Transfer Intelligence Dashboard

Base URL: `http://localhost:8000` locally, or
`https://abhishek-elets-ias-transfer-intelligence.hf.space` in production.
All v1 routes are prefixed `/api/v1`. Interactive docs at `/docs` (Swagger) and
`/redoc`.

**Auth:** JWT bearer. `POST /api/v1/auth/login` → `{ access_token }`; send
`Authorization: Bearer <token>` on every other `/api/v1` call. Routes marked
**(admin)** require `role = admin` (403 otherwise). `/health` and
`/agents/run-cycle` do not use JWT.

**Pagination:** list routes accept `page` (>= 1, default 1) and `page_size`
(1..200, default 25) and return `{ items, total, page, page_size }`.

---

## Auth
- `POST /api/v1/auth/login` — body `{ email, password }` →
  `{ access_token, token_type: "bearer" }` (401 on bad credentials, 403 if disabled)
- `GET /api/v1/auth/me` → `{ id, email, full_name, role }`

## Transfers (Explorer + Officer Profile)
- `GET /api/v1/transfers` — query: `page, page_size, q, state, district, officer,
  batch, cadre, source, status, sort, order`
  - `q` matches officer name, new/previous posting, new district (substring, case-insensitive)
  - `state, district, officer, batch, cadre, source` are substring filters;
    `district` matches new or previous district; `status` is an exact match
  - `sort`: `news_date` (default — source article publication date, unknown dates last)
    | `created_at` | `transfer_date` | `officer`; `order`: `asc` | `desc` (default)
  - → `{ items: Transfer[], total, page, page_size }`
- `GET /api/v1/transfers/{id}` → `Transfer` (404 if missing)
- `GET /api/v1/transfers/officer/{name}` → `Transfer[]` (all records whose
  officer name contains `name`, newest first)

`Transfer` = `{ id, officer_name, ias_batch, cadre, state, current_designation,
previous_district, previous_posting, new_district, new_posting, transfer_date,
effective_date, news_date, reason, notification_number, gov_order_link,
source_name, source_url, corroborating_sources: string[] | null,
discrepancies: object[] | null, status (pending|verified|conflicted|exported|
export_failed), created_at, updated_at }`

`news_date` is the publication date of the source article (the UI falls back to
it when no explicit `transfer_date` was stated).

## Dashboard stats + Analytics
- `GET /api/v1/stats` → `{ total_transfers, today, this_week, this_month,
  pending, verified, exported, by_state: {state,count}[] (top 15),
  news_total, news_today, news_week, news_pending, last_cycle_at }`
  - `today` / `news_today` use IST (Asia/Kolkata) day boundaries
  - `news_pending` = articles still in the `discovered` state
  - `last_cycle_at` = timestamp of the last completed pipeline run (null if none)
- `GET /api/v1/stats/analytics` → `{ by_state: {state,count}[],
  by_cadre: {cadre,count}[], by_district: {district,count}[],
  by_month: {month: "YYYY-MM", count}[] }`

## News feed
- `GET /api/v1/news` — query: `page, page_size, status, q, with_transfers,
  exclude_irrelevant, days, source, language`
  - `status`: exact article status
  - `q` (<= 200 chars): substring match on headline or source name
  - `with_transfers` (bool, default false): only articles that yielded >= 1 transfer record
  - `exclude_irrelevant` (bool, default false): hide `irrelevant` and `failed` articles
  - `days` (1..365): only articles published (or discovered) in the last N days
  - `source` (<= 100 chars): substring match on source name
  - `language` (<= 8 chars): exact language code, e.g. `en`, `hi`
  - Ordered newest publication first; articles without a publication date last
  - → `{ items: Article[], total, page, page_size }`

`Article` = `{ id, url, resolved_url, title, source_name, language,
published_at, status (discovered|extracted|parsed|irrelevant|failed),
relevance_score, created_at, transfers_count }`

`resolved_url` is the publisher URL behind a Google News redirect (null when
not resolved); `transfers_count` is the number of transfer records extracted
from the article.

## Google Sheets sync
- `GET /api/v1/sync/status` → `{ last_sync, last_status, exported_rows,
  failed_uploads, sheet: { connected, total_rows, error } }`
- `GET /api/v1/sync/logs` → `SyncLog[]` (last 50) =
  `{ id, status, rows_written, rows_failed, message, created_at }`
- `POST /api/v1/sync/retry` **(admin)** → `{ requeued }` — re-runs the export
  for all `verified` / `export_failed` records in the background

## Settings
- `GET /api/v1/settings` → `{ spreadsheet_id, worksheet_name, auto_export,
  credentials_uploaded, llm_provider, llm_model, discovery_interval_seconds,
  openai_configured }`
- `PUT /api/v1/settings/export` **(admin)** — body `{ spreadsheet_id?,
  worksheet_name?, auto_export? }` → the updated settings object (same shape as GET)
- `PUT /api/v1/settings/openai` **(admin)** — body `{ openai_api_key }` — sets
  (Fernet-encrypted at rest) or clears (`null`/empty) the runtime OpenAI key;
  a non-empty key switches the active provider to `openai` → updated settings object
- `POST /api/v1/settings/credentials` **(admin)** — multipart `file` upload of
  the Google service-account JSON (<= 64 KB, must contain `type:
  "service_account"`, `client_email`, `private_key`) →
  `{ uploaded, path, client_email }`
- `GET /api/v1/settings/models` → `{ providers: { id (openai|anthropic), label,
  available, model }[], active }`

## Agents (pipeline control)
- `GET /api/v1/agents/status` → `{ last_run, summary, interval_seconds,
  running, started_at, finished_at, trigger, last_error, last_result, next_run }`
  - `last_run` / `summary`: time and totals (`articles, transfers, new, exported,
    failed, remaining, budget_exhausted, seconds`) of the last completed run
  - `running, started_at, finished_at, trigger (scheduler|boot|manual|cron),
    last_error, last_result`: live in-process cycle state
  - `next_run`: when the in-process scheduler fires next (null if disabled)
- `POST /api/v1/agents/run` **(admin)** → `{ started, already_running }` —
  starts a full cycle in the background (the dashboard's "Crawl now")
- `POST /api/v1/agents/discover` **(admin)** → same as `/run`
- `POST /api/v1/agents/run-cycle` — header `x-cron-token: <CRON_TOKEN>`; no
  JWT. → `{ started, already_running }`; 401 if the token is missing/wrong or
  `CRON_TOKEN` is unset. Intended for external schedulers (e.g. Supabase
  `pg_cron` + `pg_net`).

Only one cycle runs at a time; a trigger while one is in flight returns
`{ started: false, already_running: true }`.

## Assistant (RAG)
- `POST /api/v1/chat/ask` — body `{ question }` → `{ answer, sources:
  Transfer-like[], web_sources: {title,url}[], from_web }`
  - `sources` are the transfer records the answer was grounded on;
    `from_web: true` means the local data did not cover the question and a web
    search was used (`ENABLE_WEB_FALLBACK`)

## Health (no auth)
- `GET /health` → `{ status (ok|degraded), version, database: { ok, error },
  startup: { db_ok, db_error, schema_ok, admin_ok, scheduler
  (running|disabled|unavailable), started_at }, scheduler: { enabled,
  interval_seconds, next_run } }`
  - `status` is `degraded` when the live database probe fails; the API stays up
    so the error is readable here.
