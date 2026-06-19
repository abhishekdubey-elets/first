"""News Discovery Agent.

Scans Google News (per keyword, per language) and a curated set of outlet RSS
feeds for IAS transfer news, then persists fresh, keyword-matching articles as
``Article`` rows in the DISCOVERED state for the rest of the pipeline.

Uses RSS/feeds (no scraping or API keys required) so it works out of the box and
respects sources' published feeds.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
from dateutil import parser as dateparser
from sqlalchemy import select

from app.agents.base import BaseAgent
from app.agents.sources import (
    RSS_FEEDS,
    SEARCH_KEYWORDS,
    SEARCH_KEYWORDS_HI,
)
from app.core.config import settings
from app.models.article import Article
from app.models.enums import ArticleStatus, LogLevel

# Headlines must contain at least one of these tokens to be queued (cheap filter
# before the expensive fetch + LLM steps).
_RELEVANCE_TOKENS = (
    "ias", "transfer", "transferred", "reshuffle", "posting", "collector",
    "magistrate", "cadre", "secretary", "तबादला", "स्थानांतरण", "फेरबदल",
    "जिलाधिकारी", "कलेक्टर",
)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def _google_news_url(query: str, lang: str) -> str:
    q = quote_plus(f"{query} when:1d")
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl={lang}-IN&gl=IN&ceid=IN:{lang}"
    )


def _looks_relevant(title: str) -> bool:
    low = (title or "").lower()
    return any(tok in low for tok in _RELEVANCE_TOKENS)


def _parse_date(entry) -> datetime | None:
    for key in ("published", "updated"):
        val = entry.get(key)
        if val:
            try:
                return dateparser.parse(val)
            except (ValueError, TypeError):
                continue
    return None


class DiscoveryAgent(BaseAgent):
    name = "discovery"

    def run(self) -> dict:
        """Discover and persist new candidate articles. Returns a summary."""
        candidates: list[dict] = []
        candidates.extend(self._from_google_news())
        candidates.extend(self._from_rss_feeds())

        new_count = self._persist(candidates)
        self.audit(
            "discover",
            f"Discovery run complete: {len(candidates)} candidates, {new_count} new.",
            candidates=len(candidates),
            new=new_count,
        )
        return {"candidates": len(candidates), "new": new_count}

    # --- sources -----------------------------------------------------------
    def _from_google_news(self) -> list[dict]:
        out: list[dict] = []
        langs = settings.languages or ["en"]
        for lang in langs:
            keywords = SEARCH_KEYWORDS if lang != "hi" else SEARCH_KEYWORDS_HI
            for kw in keywords:
                feed_url = _google_news_url(kw, lang)
                try:
                    feed = feedparser.parse(feed_url)
                except Exception as exc:  # noqa: BLE001
                    self.audit("discover", f"Google News fetch failed for '{kw}'",
                               level=LogLevel.WARNING, error=str(exc))
                    continue
                for e in feed.entries[: settings.DISCOVERY_MAX_ARTICLES_PER_RUN]:
                    title = e.get("title", "")
                    if not _looks_relevant(title):
                        continue
                    source = (e.get("source", {}) or {}).get("title") or "Google News"
                    out.append({
                        "url": e.get("link", ""),
                        "title": title,
                        "source_name": source,
                        "language": lang,
                        "published_at": _parse_date(e),
                        "discovery_query": kw,
                    })
        return out

    def _from_rss_feeds(self) -> list[dict]:
        out: list[dict] = []
        for source_name, feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
            except Exception:  # noqa: BLE001
                continue
            for e in feed.entries:
                title = e.get("title", "")
                if not _looks_relevant(title):
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
    def _persist(self, candidates: list[dict]) -> int:
        if self.db is None:
            return 0
        seen: set[str] = set()
        new = 0
        for c in candidates:
            url = (c.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            h = url_hash(url)
            exists = self.db.execute(
                select(Article.id).where(Article.url_hash == h)
            ).first()
            if exists:
                continue
            self.db.add(Article(
                url=url[:2048],
                url_hash=h,
                title=(c.get("title") or "")[:1024],
                source_name=(c.get("source_name") or "")[:255],
                language=c.get("language", "en"),
                published_at=c.get("published_at"),
                discovery_query=(c.get("discovery_query") or "")[:255],
                status=ArticleStatus.DISCOVERED,
            ))
            new += 1
        self.db.flush()
        return new
