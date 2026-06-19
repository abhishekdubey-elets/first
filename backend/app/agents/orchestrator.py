"""Pipeline orchestrator — wires the seven agents into one flow.

    Discovery → (per article) Extraction → Information → Dedupe/Validation
              → Sheets export → Notifications

Designed to run inside a Celery task with a sync DB session, but can also be
driven directly (e.g. from a script or a test) by passing a Session.
"""
from __future__ import annotations

from sqlalchemy import select

from app.agents.dedupe import DedupeAgent
from app.agents.discovery import DiscoveryAgent
from app.agents.extraction import ExtractionAgent
from app.agents.information import InformationAgent
from app.agents.sheets_agent import SheetsAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.article import Article
from app.models.enums import ArticleStatus, LogLevel
from app.services import llm
from app.services.audit import log_event
from app.services.notifications import notify_new_transfer

log = get_logger("orchestrator")


def discover(db) -> dict:
    """Run the Discovery Agent and persist new candidate articles."""
    return DiscoveryAgent(db).run()


def process_article(db, article: Article, *, provider=None, model=None) -> dict:
    """Run extraction → information → dedupe → export for one article."""
    extractor = ExtractionAgent(db)
    informer = InformationAgent(db)
    deduper = DedupeAgent(db)
    sheets = SheetsAgent(db)

    if not extractor.run(article):
        return {"article_id": article.id, "transfers": 0, "status": article.status.value}

    extracted = informer.run(article, provider=provider, model=model)
    model_name = model or llm.active_model(provider)

    # Dedupe/validate every extracted transfer; collect the affected records so
    # we can export and (for brand-new ones) notify.
    affected: list = []
    new_records: list = []
    for item in extracted:
        record, created = deduper.upsert(item, article=article, model=model_name)
        affected.append(record)
        if created:
            new_records.append(record)

    exported = 0
    for record in affected:
        if sheets.export(record):
            exported += 1

    for record in new_records:
        try:
            notify_new_transfer(record)
        except Exception:  # noqa: BLE001 — notifications must never break flow
            pass

    return {
        "article_id": article.id,
        "transfers": len(extracted),
        "new": len(new_records),
        "exported": exported,
        "status": article.status.value,
    }


def run_pending(db, *, limit: int | None = None, provider=None, model=None) -> dict:
    """Process all DISCOVERED articles. Returns an aggregate summary."""
    limit = limit or settings.DISCOVERY_MAX_ARTICLES_PER_RUN
    rows = db.execute(
        select(Article)
        .where(Article.status == ArticleStatus.DISCOVERED)
        .order_by(Article.created_at.asc())
        .limit(limit)
    ).scalars().all()

    totals = {"articles": 0, "transfers": 0, "new": 0, "exported": 0}
    for article in rows:
        try:
            res = process_article(db, article, provider=provider, model=model)
            totals["articles"] += 1
            totals["transfers"] += res.get("transfers", 0)
            totals["new"] += res.get("new", 0)
            totals["exported"] += res.get("exported", 0)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            article.status = ArticleStatus.FAILED
            article.error = str(exc)
            log_event(db, level=LogLevel.ERROR, agent="orchestrator",
                      action="process", message=f"Article {article.id} failed: {exc}")
            db.commit()
    log_event(db, level=LogLevel.SUCCESS, agent="orchestrator", action="run",
              message=f"Pipeline run complete: {totals}", context=totals)
    return totals
