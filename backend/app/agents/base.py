"""Base agent: shared HTTP client, logging, and audit helpers.

Every agent is a small, single-responsibility class. They are deliberately
synchronous so they compose cleanly inside Celery tasks and can be unit-tested
without an event loop.
"""
from __future__ import annotations

from urllib import robotparser
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import LogLevel
from app.services.audit import log_event

_robots_cache: dict[str, robotparser.RobotFileParser] = {}


class BaseAgent:
    name: str = "base"

    def __init__(self, db=None):
        self.db = db
        self.log = get_logger(self.name)

    # --- audit -------------------------------------------------------------
    def audit(self, action: str, message: str, *, level: LogLevel = LogLevel.INFO,
              **context) -> None:
        if self.db is not None:
            log_event(self.db, level=level, agent=self.name, action=action,
                      message=message, context=context)
        else:
            self.log.info(action, message=message, **context)

    # --- networking --------------------------------------------------------
    def http_get(self, url: str) -> httpx.Response:
        return httpx.get(
            url,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            follow_redirects=True,
        )

    def allowed_by_robots(self, url: str) -> bool:
        """Respect robots.txt before fetching a page (configurable)."""
        if not settings.RESPECT_ROBOTS_TXT:
            return True
        try:
            parts = urlparse(url)
            base = f"{parts.scheme}://{parts.netloc}"
            rp = _robots_cache.get(base)
            if rp is None:
                rp = robotparser.RobotFileParser()
                rp.set_url(f"{base}/robots.txt")
                try:
                    rp.read()
                except Exception:  # noqa: BLE001 — be permissive if unreachable
                    return True
                _robots_cache[base] = rp
            return rp.can_fetch(settings.HTTP_USER_AGENT, url)
        except Exception:  # noqa: BLE001
            return True
