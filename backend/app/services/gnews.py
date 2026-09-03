"""Resolve Google News redirect links to the publisher's real article URL.

Google News RSS feeds hand out opaque ``news.google.com/rss/articles/<id>``
links. Those can't be fetched by a bot (HTTP 400 / robots-disallowed), so the
extraction step used to fall back to the headline alone. Resolving the real URL
lets the pipeline read the full article text (far better extraction) and lets
the dashboard link straight to the publisher.

Two id formats exist:
* legacy ids embed the URL directly in the base64 payload;
* current ids (``AU_yqL...``) require one signed call to Google's
  ``batchexecute`` endpoint, using a signature/timestamp read from the article
  page.

Everything here is best-effort: any failure returns ``None`` and the caller
keeps the Google link.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_SIG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')

# Small process-level cache so a link seen by several keyword queries in the
# same cycle is only resolved once.
_cache: dict[str, str | None] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 2000

# When Google answers with a CAPTCHA/429 ("/sorry/"), every further attempt
# from this IP will fail for a while — stop trying for a cooling-off period
# instead of burning the whole per-run resolution budget.
_backoff_until = 0.0
_BACKOFF_SECONDS = 900.0


def is_rate_limited() -> bool:
    return time.monotonic() < _backoff_until


def is_google_news_url(url: str | None) -> bool:
    try:
        host = urlparse(url or "").netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return host.endswith("news.google.com")


def _article_id(url: str) -> str | None:
    m = re.search(r"/articles/([^/?#]+)", url)
    return m.group(1) if m else None


def decode_legacy_id(article_id: str) -> str | None:
    """Decode the URL embedded in a legacy Google News id (offline).

    Returns ``None`` for the newer ``AU_yqL`` ids, which need a network call.
    """
    try:
        padded = article_id + "=" * (-len(article_id) % 4)
        raw = base64.urlsafe_b64decode(padded)
    except Exception:  # noqa: BLE001
        return None
    prefix, suffix = b"\x08\x13\x22", b"\xd2\x01\x00"
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    if raw.endswith(suffix):
        raw = raw[: -len(suffix)]
    if not raw:
        return None
    length = raw[0]
    payload = raw[2 : length + 2] if length >= 0x80 else raw[1 : length + 1]
    if payload.startswith(b"AU_yqL"):
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if text.startswith("http") else None


def _resolve_signed(article_id: str, timeout: float) -> str | None:
    """Resolve a current-format id via Google's batchexecute endpoint."""
    with httpx.Client(headers=_BROWSER_HEADERS, timeout=timeout, follow_redirects=True) as client:
        page = client.get(f"https://news.google.com/articles/{article_id}")
        if page.status_code == 429 or "/sorry/" in str(page.url):
            global _backoff_until
            _backoff_until = time.monotonic() + _BACKOFF_SECONDS
            log.info("gnews_rate_limited", backoff_seconds=_BACKOFF_SECONDS)
            return None
        if page.status_code != 200:
            return None
        sig, ts = _SIG_RE.search(page.text), _TS_RE.search(page.text)
        if not (sig and ts):
            return None
        inner = json.dumps([
            "garturlreq",
            [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
              None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
            article_id, int(ts.group(1)), sig.group(1),
        ])
        payload = json.dumps([[["Fbv4je", inner, None, "generic"]]])
        resp = client.post(
            _BATCH_URL,
            data={"f.req": payload},
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        if resp.status_code != 200 or "\n\n" not in resp.text:
            return None
        data = json.loads(resp.text.split("\n\n", 1)[1])
        resolved = json.loads(data[0][2])[1]
        return resolved if isinstance(resolved, str) and resolved.startswith("http") else None


def resolve(url: str, *, timeout: float = 15.0) -> str | None:
    """Return the publisher URL behind a Google News link, or ``None``."""
    if not is_google_news_url(url):
        return None
    article_id = _article_id(url)
    if not article_id:
        return None
    with _cache_lock:
        if article_id in _cache:
            return _cache[article_id]
    result: str | None = decode_legacy_id(article_id)
    if result is None and is_rate_limited():
        return None  # don't cache: retry once the cooling-off period is over
    if result is None:
        try:
            result = _resolve_signed(article_id, timeout)
        except Exception as exc:  # noqa: BLE001 — best-effort
            log.info("gnews_resolve_failed", error=str(exc)[:200])
            result = None
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[article_id] = result
    return result
