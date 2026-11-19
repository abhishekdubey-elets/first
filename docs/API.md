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
  officer name contains `name`, newest first). Substring match, so prefer the
  officer profile below.

`Transfer` = `{ id, officer_name, officer_id, ias_batch, cadre, state, current_designation,
previous_district, previous_posting, new_district, new_posting, transfer_date,
effective_date, news_date, reason, notification_number, gov_order_link,
source_name, source_url, corroborating_sources: string[] | null,
discrepancies: object[] | null, status (pending|verified|conflicted|exported|
export_failed), created_at, updated_at }`

`news_date` is the publication date of the source article (the UI falls back to
it when no explicit `transfer_date` was stated). `officer_id` links the record to
its officer profile.

## Officers (directory + profile)
A profile per officer, assembled from their transfer records (no separate
table). Records are grouped the way the pipeline merges them: spelling variants
of a name in one state are one officer ("Mohd. Aijaz" / "Mohammad Aijaz");
identical names are joined across states only when the cadre matches and the
batch does not conflict (an AGMUT officer in Delhi, then Goa). Two batch years
never join. All dates are `YYYY-MM-DD`, derived like the public feed's `date`.

- `GET /api/v1/officers` — query: `page, page_size, q, state, batch, cadre,
  sort, order`
  - `q` matches the name or any recorded spelling variant; `state` is any state
    the officer has served in; `batch` is a year (`"2009 batch"` also works)
  - `sort`: `recent` (default, last movement first) | `movements` | `name`;
    `order` defaults to `desc`, or `asc` for `name`
  - → `{ items: OfficerSummary[], total, page, page_size }`
- `GET /api/v1/officers/{officer_id}` → `OfficerProfile` (404 if no match)
  - `officer_id` is `OfficerSummary.id` / `Transfer.officer_id`, e.g.
    `anita-sharma--uttar-pradesh`. Any spelling variant, any state the officer
    served in, or a bare URL-encoded name also resolves. When several officers
    share a name, the best match is returned (state in the id first, then the
    most recently moved) and the others are listed in `alternates`.

- `POST /api/v1/officers/{officer_id}/research` (admin) → `OfficerResearch`
  with `status: "queued"`. Puts the officer at the front of the Officer
  Research Agent's queue; the agent runs inside the crawl, not this request.
- `PATCH /api/v1/officers/{officer_id}/images` (admin) — body
  `{ image_url, hidden: true|false }` → `OfficerResearch`. Hides a wrong photo
  (or restores it); a hidden photo stays hidden when the officer is researched
  again. 404 if the image is not on this profile.

`OfficerSummary` = `{ id, name, aliases: string[], batch, cadre, state, bio,
photo_url, current_role, current_district, current_state, movements_count,
first_seen, last_movement_date, last_movement }` — `bio` is a summary built
only from the tracked records ("A. Katherine Saranya is an Indian
Administrative Service officer (Tamil Nadu cadre). Currently Commissioner,
Vellore Corporation, Tamil Nadu. 1 tracked posting change."); `photo_url` is
the best visible photo the research agent found, or null.

`OfficerProfile` = `OfficerSummary` plus `{ current: OfficerMovement | null,
timeline: OfficerMovement[] (newest first), stats: { movements,
distinct_postings, districts[], states[], role_groups: {role_group,count}[],
first_seen, last_seen, average_tenure_days | null, sources, verified_movements },
sources: {name,url}[], orders: {number,url,date}[], co_transferred: OfficerLink[],
batchmates: OfficerLink[], alternates: OfficerLink[], identity_notes: string[],
research: OfficerResearch | null }`

`OfficerResearch` = `{ status: queued | done | failed, requested_at,
researched_at, error, press: PressMention[] (newest first), images:
OfficerImage[], photo: OfficerImage | null, wikipedia: { title, url, extract,
image_url, image_page } | null }`. Non-admins never see hidden images.

`PressMention` = `{ url, title, source, published (YYYY-MM-DD), snippet,
excerpt, verdict: llm | context }` — `excerpt` is the sentence of the article
that names the officer; `verdict` says how it was judged to be about this
officer and not a namesake (the LLM, or, with no LLM configured, the excerpt
or headline naming one of the officer's places).

`OfficerImage` = `{ image_url, page_url, caption, source, origin: wikipedia |
press, hidden }` — a link to where the image was published (nothing is
copied). `press` images were matched by a caption or alt text naming the
officer and are unverified; `photo` prefers Wikipedia, then the shortest
caption.

`OfficerMovement` = `{ transfer_id, date, stated_date, movement, role,
role_group, from_posting, from_district, to_posting, to_district, state, reason,
order_number, order_link, headline, source_name, source_url, source_count,
status, is_current, tenure_days }` — `tenure_days` is the time until the next
movement, or so far for a current posting; postings on the same day share it.

`OfficerLink` = `{ id, name, batch, state, current_role, relation:
same_order | same_article | batchmate | same_name }`. `co_transferred` lists
officers in the same government order (`same_order`) or the same news report
(`same_article`); `batchmates` share both batch and cadre.

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
