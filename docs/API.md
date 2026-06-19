# API Contract — IAS Transfer Intelligence Dashboard

Base URL: `http://localhost:8000`  ·  All v1 routes are prefixed `/api/v1`.
Auth: JWT bearer. `POST /api/v1/auth/login` → `{ access_token }`; send
`Authorization: Bearer <token>` on every other call.

## Auth
- `POST /api/v1/auth/login` — body `{ email, password }` → `{ access_token, token_type }`
- `GET  /api/v1/auth/me` → `{ id, email, full_name, role }`

## Transfers (Explorer + Officer Profile)
- `GET /api/v1/transfers` — query: `page, page_size, q, state, district, officer,
  batch, cadre, source, min_confidence, status, sort(created_at|transfer_date|
  confidence|officer), order(asc|desc)` →
  `{ items: Transfer[], total, page, page_size }`
- `GET /api/v1/transfers/{id}` → `Transfer`
- `GET /api/v1/transfers/officer/{name}` → `Transfer[]` (timeline)

`Transfer` = `{ id, officer_name, ias_batch, cadre, state, current_designation,
previous_district, previous_posting, new_district, new_posting, transfer_date,
effective_date, reason, notification_number, gov_order_link, source_name,
source_url, confidence_score (0..1), corroborating_sources: string[],
discrepancies: object[], status (pending|verified|conflicted|exported|
export_failed), created_at, updated_at }`

## Dashboard stats + Analytics
- `GET /api/v1/stats` → `{ total_transfers, today, this_week, this_month, pending,
  verified, exported, avg_confidence, by_state: {state,count}[],
  confidence_distribution: {bucket,count}[] }`
- `GET /api/v1/stats/analytics` → `{ by_state[], by_cadre[], by_district[],
  by_month: {month,count}[] }`

## News feed
- `GET /api/v1/news` — query `page, page_size, status` →
  `{ items: Article[], total, page, page_size }`
  `Article` = `{ id, url, title, source_name, language, published_at, status
  (discovered|extracted|parsed|irrelevant|failed), relevance_score, created_at }`

## System logs
- `GET /api/v1/logs` — query `page, page_size, level(INFO|WARNING|ERROR|SUCCESS),
  agent, q` → `{ items: Log[], total, page, page_size }`
  `Log` = `{ id, level, agent, action, message, context, created_at }`

## Google Sheets sync
- `GET  /api/v1/sync/status` → `{ last_sync, last_status, exported_rows,
  failed_uploads, sheet: { connected, total_rows, error } }`
- `GET  /api/v1/sync/logs` → `SyncLog[]` = `{ id, status, rows_written,
  rows_failed, message, created_at }`
- `POST /api/v1/sync/retry` (admin) → `{ requeued }`

## Settings
- `GET  /api/v1/settings` → `{ spreadsheet_id, worksheet_name, auto_export,
  credentials_uploaded, llm_provider, llm_model, discovery_interval_seconds }`
- `PUT  /api/v1/settings/export` (admin) — body `{ spreadsheet_id?,
  worksheet_name?, auto_export? }`
- `POST /api/v1/settings/credentials` (admin) — multipart file upload (Google SA JSON)
- `GET  /api/v1/settings/models` → `{ providers: {id,label,available,model}[], active }`

## Agents (manual control)
- `POST /api/v1/agents/run` (admin) → `{ queued, task_id }`
- `POST /api/v1/agents/discover` (admin) → `{ queued, task_id }`

## Health
- `GET /health` → `{ status, version }`
