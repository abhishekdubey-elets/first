"""Celery tasks: the autonomous discovery + processing loop.

``run_discovery_cycle`` is the heartbeat (every 10 min via beat). It discovers
new articles then enqueues one ``process_article_task`` per article so the
heavy fetch+LLM work fans out across workers and retries independently.
"""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import select

from app.agents import orchestrator
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.article import Article
from app.models.enums import ArticleStatus

log = get_logger("tasks")


@shared_task(name="app.workers.tasks.run_discovery_cycle")
def run_discovery_cycle() -> dict:
    """Discover new articles, then enqueue processing for each."""
    with session_scope() as db:
        summary = orchestrator.discover(db)
        db.commit()
        pending = db.execute(
            select(Article.id).where(Article.status == ArticleStatus.DISCOVERED)
        ).scalars().all()

    for article_id in pending:
        process_article_task.delay(article_id)

    log.info("discovery_cycle", new=summary.get("new"), queued=len(pending))
    return {"discovered": summary, "queued": len(pending)}


@shared_task(
    name="app.workers.tasks.process_article_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def process_article_task(self, article_id: int) -> dict:
    """Run the full extraction→export pipeline for a single article."""
    try:
        with session_scope() as db:
            article = db.get(Article, article_id)
            if article is None or article.status != ArticleStatus.DISCOVERED:
                return {"article_id": article_id, "skipped": True}
            result = orchestrator.process_article(db, article)
            db.commit()
            return result
    except Exception as exc:  # noqa: BLE001
        log.warning("process_article_retry", article_id=article_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(name="app.workers.tasks.run_full_pipeline")
def run_full_pipeline() -> dict:
    """Synchronous one-shot: discover + process everything (manual trigger)."""
    with session_scope() as db:
        orchestrator.discover(db)
        db.commit()
        return orchestrator.run_pending(db)


@shared_task(name="app.workers.tasks.export_verified")
def export_verified() -> dict:
    """Re-attempt Sheets export for all VERIFIED / EXPORT_FAILED records."""
    from app.agents.sheets_agent import SheetsAgent
    from app.models.enums import TransferStatus
    from app.models.transfer import IasTransfer

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
