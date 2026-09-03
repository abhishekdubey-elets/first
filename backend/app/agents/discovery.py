"""News Discovery Agent.

Scans Google News (per keyword, per language) and a curated set of outlet RSS
feeds for IAS transfer news, then persists fresh, keyword-matching articles as
``Article`` rows in the DISCOVERED state for the rest of the pipeline.

Uses RSS/feeds (no scraping or API keys required) so it works out of the box and
respects sources' published feeds. Google News links are resolved to the
publisher's real URL (best-effort) so the extraction step can read the full
article and the dashboard can link straight to the source.
"""
from __future__ import annotations

import hashlib
import math
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx
from dateutil import parser as dateparser
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.agents.base import BaseAgent
from app.agents.sources import (
    RSS_FEEDS,
    SEARCH_KEYWORDS,
    SEARCH_KEYWORDS_HI,
)
from app.core.config import settings
from app.models.article import Article
from app.models.enums import ArticleStatus, LogLevel
from app.services import gnews

# Cheap headline filters run before the expensive fetch + LLM steps.
# "Subject" tokens say the story is about the civil service; "movement" tokens
# say it is about a posting change. Google News results already come from
# IAS-specific queries, so either kind of token is enough there; the general
# outlet RSS feeds (national news sections) need BOTH, otherwise every football
# "transfer" or bank "transfer" story would be queued.
_SUBJECT_TOKENS = (
    "ias", "i.a.s", "collector", "magistrate", "cadre", "chief secretary",
    "secretary", "commissioner", "bureaucrat", "bureaucratic", "civil servant",
    "civil service", "administrative", "district magistrate", " dm ", "sdm",
    "officer", "officers", "आईएएस", "जिलाधिकारी", "कलेक्टर", "अधिकारी",
    "प्रशासनिक", "मुख्य सचिव", "सचिव",
)
_MOVEMENT_TOKENS = (
    "transfer", "transferred", "reshuffle", "reshuffled", "posting", "posted",
    "appointed", "appointment", "shifted", "shunted", "repatriated", "relieved",
    "new collector", "new dm", "takes charge", "assumes charge", "तबादला",
    "स्थानांतरण", "फेरबदल", "तैनात", "नियुक्त", "पदस्थापना",
)
# Stories that mention transfers but are clearly not postings of officers.
_NOISE_TOKENS = (
    "football", "cricket", "transfer window", "money transfer", "bank transfer",
    "transfer fee", "ipl", "fifa", "transfer racket", "transfer deadline",
    "premier league", "la liga", "upi", "wire transfer",
)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def _lookback_days() -> int:
    hours = max(1, int(settings.DISCOVERY_LOOKBACK_HOURS))
    # Always look back at least 2 days so an hourly/daily cadence never leaves
    # a gap between the previous run's window and this one.
    return max(2, math.ceil(hours / 24))


def _google_news_url(query: str, lang: str) -> str:
    q = quote_plus(f"{query} when:{_lookback_days()}d")
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl={lang}-IN&gl=IN&ceid=IN:{lang}"
    )


def _has(tokens: tuple[str, ...], text: str) -> bool:
    return any(tok in text for tok in tokens)


def looks_relevant(title: str, *, strict: bool = False) -> bool:
    """Headline pre-filter.

    ``strict`` (used for general outlet feeds) requires both a civil-service
    subject token and a posting-movement token. Non-strict (Google News, whose
    queries are already IAS-specific) accepts either.
    """
    low = f" {(title or '').lower()} "
    if not low.strip():
        return False
    if _has(_NOISE_TOKENS, low):
        return False
    subject, movement = _has(_SUBJECT_TOKENS, low), _has(_MOVEMENT_TOKENS, low)
    return (subject and movement) if strict else (subject or movement)


def _parse_date(entry) -> datetime | None:
    """Publication date as an aware UTC datetime, never in the future."""
    for key in ("published", "updated"):
        val = entry.get(key)
        if not val:
            continue
        try:
            dt = dateparser.parse(val)
        except (ValueError, TypeError, OverflowError):
            continue
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        # Clock skew on the publisher side: clamp so a mis-dated item can't
        # pin itself to the top of a "latest first" feed.
        return min(dt, now + timedelta(minutes=5))
    return None


def _entry_source(entry) -> str | None:
    src = entry.get("source")
    if src is None:
        return None
    title = getattr(src, "title", None)
    if not title and hasattr(src, "get"):
        title = src.get("title")
    return title or None


class DiscoveryAgent(BaseAgent):
    name = "discovery"

    def fetch_feed(self, url: str):
        """Fetch a feed with a bounded timeout and parse it.

        ``feedparser.parse(url)`` would fetch with no timeout at all, which can
        wedge the whole in-process scheduler on one stalled connection.
        """
        resp = httpx.get(
            url,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            follow_redirects=True,
        )
        resp.raise_for_status()
        return feedparser.parse(resp.content)

    def run(self) -> dict:
        """Discover and persist new candidate articles. Returns a summary."""
        started = time.monotonic()
        candidates: list[dict] = []
        candidates.extend(self._from_google_news())
        candidates.extend(self._from_rss_feeds())

        new_count, resolved = self._persist(candidates)
        self.audit(
            "discover",
            f"Discovery run complete: {len(candidates)} candidates, {new_count} new.",
            candidates=len(candidates),
            new=new_count,
            resolved_links=resolved,
            seconds=round(time.monotonic() - started, 1),
        )
        return {"candidates": len(candidates), "new": new_count, "resolved_links": resolved}

    # --- sources -----------------------------------------------------------
    def _from_google_news(self) -> list[dict]:
        out: list[dict] = []
        langs = settings.languages or ["en"]
        for lang in langs:
            keywords = SEARCH_KEYWORDS if lang != "hi" else SEARCH_KEYWORDS_HI
            for kw in keywords:
                feed_url = _google_news_url(kw, lang)
                try:
                    feed = self.fetch_feed(feed_url)
                except Exception as exc:  # noqa: BLE001
                    self.audit("discover", f"Google News fetch failed for '{kw}'",
                               level=LogLevel.WARNING, error=str(exc)[:300])
                    continue
                for e in feed.entries[: settings.DISCOVERY_MAX_ARTICLES_PER_RUN]:
                    title = e.get("title", "")
                    if not looks_relevant(title):
                        continue
                    out.append({
                        "url": e.get("link", ""),
                        "title": title,
                        "source_name": _entry_source(e) or "Google News",
                        "language": lang,
                        "published_at": _parse_date(e),
                        "discovery_query": kw,
                    })
        return out

    def _from_rss_feeds(self) -> list[dict]:
        out: list[dict] = []
        for source_name, feed_url in RSS_FEEDS:
            try:
                feed = self.fetch_feed(feed_url)
            except Exception as exc:  # noqa: BLE001
                self.audit("discover", f"RSS fetch failed for {source_name}",
                           level=LogLevel.WARNING, error=str(exc)[:300])
                continue
            for e in feed.entries:
                title = e.get("title", "")
                if not looks_relevant(title, strict=True):
                    continue
                out.append({
                    "url": e.get("link", ""),
                    "title": title,
                    "source_name": source_name,
                    "language": "en",
                    "published_at": _parse_date(e),
                    "discovery_query": "rss",
                })
        return out

    # --- persistence -------------------------------------------------------
    def _exists(self, url: str, h: str) -> bool:
        """Already in the feed? Match the URL itself (Google link or publisher
        link, whichever we stored) as well as the hash used as the dedupe key."""
        return self.db.execute(
            select(Article.id).where(or_(
                Article.url_hash == h, Article.url == url, Article.resolved_url == url,
            ))
        ).first() is not None

    def _insert(self, article: Article) -> bool:
        """Insert inside a savepoint so one duplicate can't abort the batch."""
        try:
            with self.db.begin_nested():
                self.db.add(article)
                self.db.flush()
            return True
        except IntegrityError:
            return False

    def _persist(self, candidates: list[dict]) -> tuple[int, int]:
        """Insert unseen candidates. Returns (new rows, resolved Google links).

        Newest candidates are inserted first so that, when a run is cut short,
        the latest news is what made it into the feed.
        """
        if self.db is None:
            return 0, 0
        floor = datetime.min.replace(tzinfo=timezone.utc)
        candidates = sorted(
            candidates, key=lambda c: c.get("published_at") or floor, reverse=True,
        )
        seen: set[str] = set()
        new = resolved = 0
        resolve_budget = settings.DISCOVERY_MAX_LINK_RESOLUTIONS_PER_RUN
        for c in candidates:
            url = (c.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            h = url_hash(url)
            if self._exists(url, h):
                continue

            # Resolve the publisher URL behind Google News links, and de-dupe
            # against the same story found directly via an outlet's own feed.
            resolved_url: str | None = None
            if settings.DISCOVERY_RESOLVE_GOOGLE_LINKS and resolve_budget > 0 \
                    and gnews.is_google_news_url(url):
                resolve_budget -= 1
                resolved_url = gnews.resolve(url)
                if resolved_url:
                    resolved += 1
                    rh = url_hash(resolved_url)
                    if rh in seen or resolved_url in seen or self._exists(resolved_url, rh):
                        continue
                    seen.add(rh)
                    seen.add(resolved_url)
                    h = rh  # dedupe key is the real article, not the redirect

            inserted = self._insert(Article(
                url=url[:2048],
                url_hash=h,
                resolved_url=resolved_url[:2048] if resolved_url else None,
                title=(c.get("title") or "")[:1024],
                source_name=(c.get("source_name") or "")[:255],
                language=c.get("language", "en"),
                published_at=c.get("published_at"),
                discovery_query=(c.get("discovery_query") or "")[:255],
                status=ArticleStatus.DISCOVERED,
            ))
            if inserted:
                new += 1
        self.db.flush()
        return new, resolved
