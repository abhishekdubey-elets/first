"""Discovery + processing pipeline — runs in-process (no Celery / no Redis).

A full cycle = discover new articles, process pending ones (newest first) into
structured transfers, web-enrich records with gaps, then purge stale news.
Extraction is an OpenAI API call, so the whole cycle runs comfortably inside
the API process — driven by the in-process scheduler (see ``app.main``), by an
external cron hitting ``POST /api/v1/agents/run-cycle``, or on demand from the
dashboard ("Crawl now").

Only ONE cycle runs at a time: the scheduler, the cron endpoint and the
dashboard button can all fire, and two concurrent cycles would race on article
inserts. ``run_discovery_cycle`` takes a process-wide lock and reports
``skipped`` if another cycle is already in flight. ``cycle_status()`` exposes the
live state for the dashboard's pipeline card.
"""
from __future__ import annotations

import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, or_, select, update

from app.agents import orchestrator
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.article import Article
from app.models.transfer import IasTransfer

log = get_logger("pipeline")

# Backwards-compatible alias; the retention window is configurable now.
NEWS_RETENTION_DAYS = settings.NEWS_RETENTION_DAYS

_cycle_lock = threading.Lock()
_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "last_error": None,
    "trigger": None,
}


def cycle_status() -> dict[str, Any]:
    """Snapshot of the in-process cycle state (JSON-serialisable)."""
    with _state_lock:
        return dict(_state)


def _set_state(**changes: Any) -> None:
    with _state_lock:
        _state.update(changes)


def enrich_incomplete(limit: int | None = None) -> dict:
    """Web-search to fill gaps (from/to/state/date) on records that are missing them.

    Bounded per call AND per record: each record gets at most
    ``ENRICHMENT_MAX_ATTEMPTS`` searches (newest records first). Fields still
    empty after that are genuinely unknown ("no info" in the UI) and the record
    stops costing a web search + LLM call every cycle.
    """
    from app.agents.enrichment import EnrichmentAgent

    limit = limit or settings.ENRICHMENT_BATCH_SIZE
    with session_scope() as db:
        agent = EnrichmentAgent(db)
        rows = db.execute(
            select(IasTransfer).where(
                IasTransfer.enrichment_attempts < settings.ENRICHMENT_MAX_ATTEMPTS,
                or_(
                    IasTransfer.state.is_(None),
                    IasTransfer.transfer_date.is_(None),
                    and_(IasTransfer.new_district.is_(None), IasTransfer.new_posting.is_(None)),
                    and_(IasTransfer.previous_district.is_(None), IasTransfer.previous_posting.is_(None)),
                ),
            ).order_by(IasTransfer.created_at.desc()).limit(limit)
        ).scalars().all()
        enriched = 0
        now = datetime.now(timezone.utc)
        for r in rows:
            r.enrichment_attempts = (r.enrichment_attempts or 0) + 1
            r.last_enriched_at = now
            try:
                if agent.enrich(r):
                    enriched += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("enrich_error", officer=r.officer_name, error=str(exc))
        db.commit()
    return {"candidates": len(rows), "enriched": enriched}


def purge_expired_news() -> dict:
    """Delete news articles that have been in the feed longer than the retention window.

    "Arrived in the feed" is ``Article.created_at`` (discovery time), so an
    article is removed once ``NEWS_RETENTION_DAYS`` have passed since it first
    appeared. Any extracted ``IasTransfer`` rows are detached first
    (``article_id`` -> NULL) rather than cascade-deleted, so the structured
    transfer intelligence and its Google-Sheets export survive the purge. A
    bulk DELETE is used (not ORM ``session.delete``) precisely to bypass the
    ``delete-orphan`` cascade on the relationship.
    """
    days = settings.NEWS_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with session_scope() as db:
        expired_ids = select(Article.id).where(Article.created_at < cutoff)
        db.execute(
            update(IasTransfer)
            .where(IasTransfer.article_id.in_(expired_ids))
            .values(article_id=None)
        )
        deleted = db.execute(
            delete(Article).where(Article.created_at < cutoff)
        ).rowcount
    log.info("purge_expired_news", deleted=deleted, retention_days=days)
    return {"deleted": deleted, "retention_days": days}


def requeue_failed(max_age_days: int = 2) -> int:
    """Give recently FAILED articles another chance.

    An article fails when the fetch or the LLM call raised — usually a
    transient problem (LLM outage, missing/expired API key, timeout). Rather
    than losing that news for good, recent failures are put back in the queue
    each cycle; once the underlying problem is fixed they flow through. Old
    failures are left alone (and purged with the rest of the feed).
    """
    from app.models.enums import ArticleStatus

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    with session_scope() as db:
        n = db.execute(
            update(Article)
            .where(Article.status == ArticleStatus.FAILED, Article.created_at >= cutoff)
            .values(status=ArticleStatus.DISCOVERED)
        ).rowcount
    if n:
        log.info("requeued_failed_articles", count=n)
    return n


def _run_cycle_locked(trigger: str) -> dict:
    result: dict[str, Any] = {}
    try:
        with session_scope() as db:
            result["discovered"] = orchestrator.discover(db)
            db.commit()
    except Exception as exc:  # noqa: BLE001 — still process what is already queued
        log.error("discovery_failed", error=str(exc)[:500])
        result["discovered"] = {"candidates": 0, "new": 0, "error": str(exc)[:300]}
    try:
        result["requeued"] = requeue_failed()
    except Exception as exc:  # noqa: BLE001
        log.warning("requeue_failed_error", error=str(exc))
        result["requeued"] = 0
    with session_scope() as db:
        result["processed"] = orchestrator.run_pending(
            db, time_budget_seconds=settings.CYCLE_TIME_BUDGET_SECONDS
        )
    try:
        result["enriched"] = enrich_incomplete()
    except Exception as exc:  # noqa: BLE001 — enrichment is optional polish
        log.warning("enrich_incomplete_failed", error=str(exc))
        result["enriched"] = {"candidates": 0, "enriched": 0, "error": str(exc)[:300]}
    try:
        result["purged"] = purge_expired_news()
    except Exception as exc:  # noqa: BLE001 — a purge failure must not break the cycle
        log.warning("purge_expired_news_failed", error=str(exc))
        result["purged"] = {"deleted": 0, "error": str(exc)[:300]}
    log.info("discovery_cycle", trigger=trigger, **result)
    return result


def run_discovery_cycle(trigger: str = "scheduler") -> dict:
    """Run one full cycle unless one is already running (then report skipped)."""
    if not _cycle_lock.acquire(blocking=False):
        log.info("discovery_cycle_skipped", reason="already running", trigger=trigger)
        return {"skipped": True, "reason": "A discovery cycle is already running."}
    started = datetime.now(timezone.utc)
    _set_state(running=True, started_at=started.isoformat(), trigger=trigger, last_error=None)
    try:
        result = _run_cycle_locked(trigger)
        _set_state(last_result=result)
        return result
    except Exception as exc:  # noqa: BLE001 — record, then re-raise for the caller's logs
        err = f"{type(exc).__name__}: {exc}"
        log.error("discovery_cycle_failed", error=err, trace=traceback.format_exc()[-1500:])
        _set_state(last_error=err[:500])
        raise
    finally:
        _set_state(running=False, finished_at=datetime.now(timezone.utc).isoformat())
        _cycle_lock.release()


def export_verified() -> dict:
    """Re-attempt Google Sheets export for all VERIFIED / EXPORT_FAILED records."""
    from app.agents.sheets_agent import SheetsAgent
    from app.models.enums import TransferStatus

    exported = 0
    with session_scope() as db:
        agent = SheetsAgent(db)
        rows = db.execute(
            select(IasTransfer).where(
                IasTransfer.status.in_(
                    (TransferStatus.VERIFIED, TransferStatus.EXPORT_FAILED)
                )
            )
        ).scalars().all()
        for r in rows:
            if agent.export(r):
                exported += 1
        db.commit()
    return {"exported": exported}
