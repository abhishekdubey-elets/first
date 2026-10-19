# Integrating the IAS Transfer API with an existing CMS

How to pull live IAS officer transfer news and structured transfer records into a
CMS or frontend you already have. There are two ways in: a public drop-in JSON
feed in the CXO Movement Tracker format, and the full authenticated REST API.

| | |
|---|---|
| Base URL | `https://abhishek-elets-ias-transfer-intelligence.hf.space` |
| Prefix | `/api/v1` (except `/health`) |
| Auth | public for the `.json` feeds; bearer JWT (24 h) for the REST API |
| Data refresh | once every 24 hours |
| Interactive reference | `/docs` on the base URL |

## Quickest path: the drop-in JSON feed

The portal already reads CXO Movement Tracker feeds shaped like
`cxo-movement-tracker.vercel.app/api/v1/bfsi.json`. These endpoints publish the
IAS records in **exactly that shape**, so the portal can read them by changing
only the URL. No login, no token, no CORS setup.

| Endpoint | What it returns |
|---|---|
| `GET /api/v1/ias.json` | every record, newest first |
| `GET /api/v1/ias_latest.json` | the 50 newest records |
| `GET /api/v1/index.json` | counts and the endpoint list |

```
https://abhishek-elets-ias-transfer-intelligence.hf.space/api/v1/ias.json
https://abhishek-elets-ias-transfer-intelligence.hf.space/api/v1/ias_latest.json
https://abhishek-elets-ias-transfer-intelligence.hf.space/api/v1/index.json
```

Same envelope, same twelve record keys in the same order:

```json
{
  "api_version": "1",
  "source": "IAS Transfer Intelligence",
  "sector": "Government",
  "updated": "2026-09-03T07:05:48+00:00",
  "count": 50,
  "records": [
    {
      "date": "2026-09-02",
      "person": "Rajeev Singh Thakur",
      "movement": "Appointment",
      "role": "Chief Secretary, Manipur",
      "role_group": "Chief Secretary",
      "company": "Government of Manipur",
      "moved_from": "",
      "moved_from_source": "",
      "sector": "Government",
      "region": "India",
      "headline": "IAS Rajeev Singh Thakur Appointed Manipur Chief Secretary",
      "source_count": 2,

      "id": 2,
      "state": "Manipur",
      "cadre": "Manipur",
      "batch": "",
      "district": "Imphal",
      "moved_from_district": "",
      "order_number": "",
      "order_link": "",
      "source": "APAC Media",
      "status": "exported",
      "updated": "2026-09-02T09:44:21+00:00"
    }
  ]
}
```

The first twelve keys are the CXO contract. Everything after them is
IAS-specific and additive: code written against the tracker format ignores it.

### How the IAS data maps onto the tracker's columns

| Column | Filled with |
|---|---|
| `date` | parseable `transfer_date`, else `effective_date`, else the article's publication date, else when the record was created |
| `person` | officer name |
| `movement` | `Transfer`, `Appointment`, `Promotion`, `Retirement`, `Resignation`, `Re-appointment`. `Transfer` is added to the tracker's vocabulary because it is the core event here |
| `role` | new posting, else current designation, else `Collector, {district}` |
| `role_group` | `Chief Secretary`, `District Magistrate / Collector`, `Secretary`, `Commissioner`, `Sub-Divisional Magistrate`, `Managing Director / CEO`, `Director`, `Chairman`, `Other`. English and Hindi titles both map |
| `company` | the employing government, e.g. `Government of Bihar` |
| `moved_from` | previous district, else previous posting |
| `moved_from_source` | `article` when a previous posting is known, else empty |
| `sector` | always `Government` |
| `region` | always `India` |
| `headline` | the source article headline. A reshuffle article covering several officers gives the same headline to each of its records |
| `source_count` | how many articles reported this transfer |

### Query parameters

| Param | Applies to | Notes |
|---|---|---|
| `limit` | `ias.json`, `ias_latest.json` | default 2000 / 50 |
| `days` | `ias.json` | only records added in the last N days |

### Access

Open by default, like the tracker it mirrors, because it republishes news that
is already public. `Cache-Control: public, max-age=900` and
`Access-Control-Allow-Origin: *` are set, so a browser on any domain can fetch
it and a CDN will cache it.

To lock it down, set either Space secret:

- `FEED_TOKEN` — callers must then send `?token=...` or an `x-feed-token` header
- `PUBLIC_FEED_ENABLED=false` — turns the three endpoints off entirely

---

## The full REST API

Use this when the portal needs filtering, pagination, search or officer pages
that the flat feed does not cover.

Two collections matter for a website:

- **News** (`/api/v1/news`) — the crawled articles, newest first. A live
  "latest IAS transfer news" block.
- **Transfers** (`/api/v1/transfers`) — the extracted records: officer, batch,
  cadre, from/to posting, dates, source. Tables, officer pages, search.

---

## 1. Allow your origin (browser calls only)

If any request is made **from the browser**, add the CMS origin to the Space
secret `BACKEND_CORS_ORIGINS` (Settings → Variables and secrets). Comma
separated, exact origins, no trailing slash, no wildcards:

```
https://www.yoursite.com,https://staging.yoursite.com,http://localhost:3000
```

Saving restarts the Space (~1 minute).

Skip this entirely if you call the API from your CMS server — server-to-server
requests are not subject to CORS.

## 2. Pick an integration shape

**Server-side proxy (recommended).** Your CMS backend logs in once, caches the
token and the responses, and renders markup or exposes its own small endpoint.
The password never reaches the browser, you control caching, CORS never applies.

**Direct from the browser.** Fine for an internal dashboard behind your own
login. Requires step 1.

Never put the API email and password in client-side JavaScript or a public
config file.

## 3. Get a token

```bash
curl -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"...","password":"..."}'
# {"access_token":"eyJ...","token_type":"bearer"}
```

Send `Authorization: Bearer <token>` on every other call. `GET /api/v1/auth/me`
confirms a token is still valid and returns `{id, email, full_name, role}`
(`admin` or `viewer`).

Create a **viewer** account for the website rather than reusing the admin login,
so a leaked token cannot trigger crawls or change settings.

## 4. First call (Node)

```js
const BASE = "https://abhishek-elets-ias-transfer-intelligence.hf.space";
let token = null, tokenExp = 0;

async function getToken() {
  if (token && Date.now() < tokenExp) return token;
  const r = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: process.env.IAS_EMAIL, password: process.env.IAS_PASSWORD }),
  });
  if (!r.ok) throw new Error(`login failed: ${r.status}`);
  token = (await r.json()).access_token;
  tokenExp = Date.now() + 23 * 60 * 60 * 1000;   // refresh an hour early
  return token;
}

async function api(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
  );
  const url = `${BASE}/api/v1${path}${qs.toString() ? `?${qs}` : ""}`;
  let r = await fetch(url, { headers: { Authorization: `Bearer ${await getToken()}` } });
  if (r.status === 401) {                        // expired: retry once
    token = null;
    r = await fetch(url, { headers: { Authorization: `Bearer ${await getToken()}` } });
  }
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

const news = await api("/news", { page_size: 10, days: 7, exclude_irrelevant: true });
```

---

## Endpoints

### `GET /api/v1/news`

Newest first by publication date; articles without one are ordered last by
discovery time. Returns `{items, total, page, page_size}`.

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | int ≥ 1 | 1 | |
| `page_size` | int 1–200 | 25 | hard cap 200 |
| `q` | string | — | headline or source name, case-insensitive |
| `days` | int 1–365 | — | only the last N days |
| `exclude_irrelevant` | bool | false | hides non-transfer news — **use on public pages** |
| `with_transfers` | bool | false | only articles that produced a record |
| `status` | enum | — | `discovered`/`extracted`/`parsed`/`irrelevant`/`failed` |
| `source` | string | — | partial publisher name |
| `language` | string | — | `en` or `hi` |

`Article`: `id` int, `url`, `resolved_url`?, `title`?, `source_name`?,
`language`?, `published_at`? ISO, `status`, `relevance_score`? float,
`created_at` ISO, `transfers_count` int.

Always link to `resolved_url || url` — a bare `url` is often a Google News
redirect that will not open cleanly.

### `GET /api/v1/transfers`

Returns `{items, total, page, page_size}`. All text filters are partial and
case-insensitive.

| Param | Type | Default | Notes |
|---|---|---|---|
| `page`, `page_size` | int | 1, 25 | as above |
| `q` | string | — | officer, posting or destination district |
| `state` | string | — | e.g. `Bihar` |
| `district` | string | — | matches from **or** to district |
| `officer` | string | — | officer name |
| `batch` | string | — | IAS batch year |
| `cadre` | string | — | state cadre |
| `source` | string | — | publisher name |
| `status` | enum | — | `pending`/`verified`/`conflicted`/`exported`/`export_failed` |
| `sort` | enum | `news_date` | `news_date`/`created_at`/`transfer_date`/`officer` |
| `order` | enum | `desc` | `asc`/`desc` |

### `GET /api/v1/transfers/{id}`

One record, or 404.

### `GET /api/v1/transfers/officer/{name}`

Every record for one officer, newest first, as a plain array (no pagination
wrapper). URL-encode the name.

**Substring match** — `/officer/Amit%20Kumar` also returns "Amit Kumari".
Filter for an exact case-insensitive match before rendering an officer page.

### `GET /api/v1/stats`

Counters for a summary strip; day boundaries follow IST.

```json
{
  "total_transfers": 412, "today": 7, "this_week": 41, "this_month": 118,
  "pending": 96, "verified": 210, "exported": 106,
  "by_state": [{"state": "Uttar Pradesh", "count": 63}],
  "news_total": 1840, "news_today": 36, "news_week": 185, "news_pending": 0,
  "last_cycle_at": "2026-09-02T08:58:04+00:00"
}
```

### `GET /api/v1/stats/analytics`

`by_state`, `by_cadre`, `by_district`, `by_month` (`{month: "2026-09", count}`).

### `GET /health` — no token, no prefix

Uptime monitoring and deployment checks. `status` is `ok` or `degraded`; the
body also reports the active model, the scheduler's next run, and the last
cycle's counts.

### `GET /api/v1/agents/status`

Crawl state for an "updated" line: `last_run`, `next_run`, `running`,
`last_error`, `summary` of the last cycle.

### `POST /api/v1/agents/run` — admin only

Starts a crawl in the background, returns `{started, already_running}`. Only one
cycle runs at a time. **Never call this on a page load** — a cycle takes up to
twenty minutes and costs LLM credits. The scheduler already runs it hourly.

### `POST /api/v1/agents/run-cycle` — cron token

Same, for external schedulers. No login; send `x-cron-token: <CRON_TOKEN>`.

Also available for internal admin screens: `GET /api/v1/sync/status` and
`/sync/logs`, `GET /api/v1/settings`, and `POST /api/v1/chat/ask` with
`{"question": "..."}`.

---

## Field reference — `Transfer`

| Field | Type | Notes |
|---|---|---|
| `id` | int | stable identifier |
| `officer_name` | string | always present |
| `ias_batch` | string? | batch year as written |
| `cadre`, `state` | string? | state validated against Indian states/UTs |
| `current_designation` | string? | |
| `previous_district`, `previous_posting` | string? | moved from |
| `new_district`, `new_posting` | string? | moved to |
| `transfer_date`, `effective_date` | string? | **free text** copied from the article — do not parse |
| `news_date` | ISO datetime? | publication date of the source article — sortable |
| `reason` | string? | |
| `notification_number`, `gov_order_link` | string? | government order reference |
| `source_name`, `source_url` | string? | publisher and article link |
| `corroborating_sources` | string[] | every article reporting this transfer |
| `discrepancies` | object[] | fields where sources disagree |
| `status` | enum | see below |
| `created_at`, `updated_at` | ISO datetime | |

**Transfer status:** `pending` (one source), `verified` (corroborated or high
confidence), `conflicted` (sources disagree — see `discrepancies`), `exported`
(written to the Google Sheet), `export_failed` (will retry).

For a public page, filtering to `verified` + `exported` is the safe choice.

**Article status:** `discovered` → `extracted` → `parsed`. `irrelevant` means it
was judged not to be transfer news; `failed` means fetching/reading errored and
it will be retried.

---

## Recipes

```js
// Latest news block
const { items } = await api("/news", { page_size: 8, days: 7, exclude_irrelevant: true });
items.map(a => ({
  title:  a.title || "Untitled",
  href:   a.resolved_url || a.url,
  source: a.source_name || "Unknown source",
  when:   new Date(a.published_at || a.created_at),
  isNew:  Date.now() - new Date(a.published_at || a.created_at) < 864e5,
  badge:  a.transfers_count > 0 ? `${a.transfers_count} transfers` : null,
}));

// Recent transfers table
const { items, total } = await api("/transfers", {
  page: 1, page_size: 20, sort: "news_date", order: "desc",
});

function displayDate(t) {                       // real date, then news date, then raw text
  const d = Date.parse(t.transfer_date);
  if (!Number.isNaN(d)) return new Date(d).toLocaleDateString("en-IN");
  if (t.news_date) return new Date(t.news_date).toLocaleDateString("en-IN");
  return t.transfer_date || "—";
}
const from = t.previous_district || t.previous_posting || "—";
const to   = t.new_district      || t.new_posting      || "—";

// Officer profile — tighten the loose backend match
const rows  = await api(`/transfers/officer/${encodeURIComponent(name)}`);
const exact = rows.filter(
  t => t.officer_name.trim().toLowerCase() === name.trim().toLowerCase()
);

// Landing pages
await api("/transfers", { state: "Bihar", page_size: 50 });
await api("/transfers", { district: "Patna", page_size: 50 });
await api("/transfers", { q: "Collector", page_size: 50 });
```

---

## PHP / WordPress

Caches the token for 23 hours and each response for 15 minutes, which matches
the hourly refresh.

```php
<?php
define('IAS_API', 'https://abhishek-elets-ias-transfer-intelligence.hf.space');

function ias_token() {
    $t = get_transient('ias_token');
    if ($t) return $t;

    $res = wp_remote_post(IAS_API . '/api/v1/auth/login', [
        'headers' => ['Content-Type' => 'application/json'],
        'body'    => wp_json_encode([
            'email'    => IAS_API_EMAIL,      // define in wp-config.php
            'password' => IAS_API_PASSWORD,
        ]),
        'timeout' => 20,
    ]);
    if (is_wp_error($res) || wp_remote_retrieve_response_code($res) !== 200) return null;

    $t = json_decode(wp_remote_retrieve_body($res), true)['access_token'];
    set_transient('ias_token', $t, 23 * HOUR_IN_SECONDS);
    return $t;
}

function ias_get($path, $args = [], $ttl = 900) {
    $key = 'ias_' . md5($path . serialize($args));
    $hit = get_transient($key);
    if ($hit !== false) return $hit;

    $token = ias_token();
    if (!$token) return null;

    $url = IAS_API . '/api/v1' . $path . '?' . http_build_query($args);
    $res = wp_remote_get($url, [
        'headers' => ['Authorization' => 'Bearer ' . $token], 'timeout' => 20,
    ]);

    if (wp_remote_retrieve_response_code($res) === 401) {   // expired: retry once
        delete_transient('ias_token');
        $res = wp_remote_get($url, [
            'headers' => ['Authorization' => 'Bearer ' . ias_token()], 'timeout' => 20,
        ]);
    }
    if (is_wp_error($res) || wp_remote_retrieve_response_code($res) !== 200) return null;

    $data = json_decode(wp_remote_retrieve_body($res), true);
    set_transient($key, $data, $ttl);
    return $data;
}

// Shortcode: [ias_news count="6"]
add_shortcode('ias_news', function ($atts) {
    $a    = shortcode_atts(['count' => 6, 'days' => 7], $atts);
    $data = ias_get('/news', [
        'page_size'          => (int) $a['count'],
        'days'               => (int) $a['days'],
        'exclude_irrelevant' => 'true',
    ]);
    if (empty($data['items'])) return '<p>No transfer news right now.</p>';

    $out = '<ul class="ias-news">';
    foreach ($data['items'] as $item) {
        $href = $item['resolved_url'] ?: $item['url'];
        $when = $item['published_at'] ?: $item['created_at'];
        $out .= sprintf(
            '<li><a href="%s" target="_blank" rel="noopener">%s</a>'
            . '<span class="meta">%s &middot; %s</span></li>',
            esc_url($href),
            esc_html($item['title'] ?: 'Untitled'),
            esc_html($item['source_name'] ?: 'Unknown'),
            esc_html(human_time_diff(strtotime($when)) . ' ago')
        );
    }
    return $out . '</ul>';
});
```

Credentials go in `wp-config.php`, not the plugin file:

```php
define('IAS_API_EMAIL', 'cms@digitallearning.in');
define('IAS_API_PASSWORD', '...');
```

---

## Errors

| Code | Means | Do this |
|---|---|---|
| 401 | missing/expired/wrong token | log in again, retry once |
| 403 | endpoint needs admin role | use an admin account or drop the call |
| 404 | no such record | show an empty state |
| 422 | parameter failed validation | check types and ranges |
| 500 | server error | retry after a pause; check `/health` |

Errors return `{"detail": "..."}` **except 422, which returns an array** of
validation objects. Rendering `detail` straight into a template breaks on that
response:

```js
const detail  = body?.detail;
const message = typeof detail === "string" ? detail : "Could not load transfer data.";
```

---

## Gotchas

| Behaviour | What to do |
|---|---|
| `transfer_date` is free text | The LLM copies it verbatim ("with immediate effect", "15 Aug"). Sort/filter on `news_date`; display `transfer_date` with a fallback. |
| Officer lookup is a substring match | Filter for the exact name client-side. |
| Data changes hourly at most | Cache 5–15 minutes; polling faster gains nothing. |
| First request after a quiet period can be slow | The container may need seconds to wake. Use a 20 s timeout, serve stale cache on failure. |
| Many fields are nullable | Extraction is best-effort. Template every field with a fallback. |
| `page_size` caps at 200 | Above that returns 422. Page using `total`. |
| Records improve over time | Fields fill in as more sources report. Key your cache on `id` and refresh rather than copying records permanently into CMS tables. |
