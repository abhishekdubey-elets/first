"""Discovery + processing pipeline — runs in-process (no Celery / no Redis).

A full cycle = discover new articles, then process every pending one to a
structured transfer. Because extraction is now an OpenAI API call (fast, not a
slow local model), the whole cycle runs comfortably as a FastAPI background
task — there is no need for a broker or a separate worker process.

Triggered:
* on a schedule by an external cron (e.g. Supabase pg_cron) pinging
  ``POST /api/v1/agents/run-cycle``;
* on demand from the dashboard ("Run agents now").
"""
from __future__ import annotations

from sqlalchemy import and_, or_, select

from app.agents import orchestrator
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.transfer import IasTransfer

log = get_logger("pipeline")


def enrich_incomplete(limit: int = 25) -> dict:
    """Web-search to fill gaps (from/to/state/date) on records that are missing them.

    Bounded per call so the cron stays cheap; runs again next cycle, so records
    keep getting another chance until filled. Fields still empty after a search
    are genuinely unknown ("no info" in the UI).
    """
    from app.agents.enrichment import EnrichmentAgent

    with session_scope() as db:
        agent = EnrichmentAgent(db)
        rows = db.execute(
            select(IasTransfer).where(or_(
                IasTransfer.state.is_(None),
                IasTransfer.transfer_date.is_(None),
                and_(IasTransfer.new_district.is_(None), IasTransfer.new_posting.is_(None)),
                and_(IasTransfer.previous_district.is_(None), IasTransfer.previous_posting.is_(None)),
            )).order_by(IasTransfer.created_at.desc()).limit(limit)
        ).scalars().all()
        enriched = 0
        for r in rows:
            try:
                if agent.enrich(r):
                    enriched += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("enrich_error", officer=r.officer_name, error=str(exc))
        db.commit()
    return {"candidates": len(rows), "enriched": enriched}


def run_discovery_cycle() -> dict:
    """Discover new articles, process pending ones, then enrich any gaps via web."""
    with session_scope() as db:
        summary = orchestrator.discover(db)
        db.commit()
    with session_scope() as db:
        processed = orchestrator.run_pending(db)
    enriched = enrich_incomplete()
    log.info("discovery_cycle", discovered=summary, processed=processed, enriched=enriched)
    return {"discovered": summary, "processed": processed, "enriched": enriched}


def export_verified() -> dict:
    """Re-attempt Google Sheets export for all VERIFIED / EXPORT_FAILED records."""
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
