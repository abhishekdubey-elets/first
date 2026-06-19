"""Seed a few demo transfer + article rows so the dashboard isn't empty.

Run after init_db: `python -m scripts.seed_demo`. Safe to run repeatedly
(skips if demo rows already exist).
"""
from __future__ import annotations

from app.agents.dedupe import compute_dedup_key
from app.core.database import session_scope
from app.models import Article, IasTransfer
from app.models.enums import ArticleStatus, TransferStatus
from app.schemas.transfer import ExtractedTransfer

_DEMO = [
    ExtractedTransfer(
        officer_name="Anita Sharma", ias_batch="2009", cadre="Uttar Pradesh",
        state="Uttar Pradesh", current_designation="District Magistrate",
        previous_district="Varanasi", previous_posting="DM Varanasi",
        new_district="Lucknow", new_posting="DM Lucknow",
        transfer_date="2026-06-15", effective_date="2026-06-18",
        notification_number="UP/APP/2026/441", confidence_score=0.92,
    ),
    ExtractedTransfer(
        officer_name="Rohit Menon", ias_batch="2012", cadre="Maharashtra",
        state="Maharashtra", current_designation="Collector",
        previous_district="Pune", previous_posting="Collector Pune",
        new_district="Nagpur", new_posting="Collector Nagpur",
        transfer_date="2026-06-14", confidence_score=0.81,
    ),
]


def main() -> None:
    with session_scope() as db:
        for i, e in enumerate(_DEMO):
            key = compute_dedup_key(e)
            if db.query(IasTransfer).filter_by(dedup_key=key).first():
                continue
            art = Article(
                url=f"https://example.com/demo/{i}",
                url_hash=f"demo-{i}",
                title=f"Demo: {e.officer_name} transferred",
                source_name="Demo Wire",
                status=ArticleStatus.PARSED,
            )
            db.add(art)
            db.flush()
            db.add(IasTransfer(
                officer_name=e.officer_name, ias_batch=e.ias_batch, cadre=e.cadre,
                state=e.state, current_designation=e.current_designation,
                previous_district=e.previous_district, previous_posting=e.previous_posting,
                new_district=e.new_district, new_posting=e.new_posting,
                transfer_date=e.transfer_date, effective_date=e.effective_date,
                notification_number=e.notification_number,
                source_name=art.source_name, source_url=art.url,
                confidence_score=e.confidence_score, dedup_key=key,
                corroborating_sources=[art.url], discrepancies=[],
                extracted_by_model="seed", article_id=art.id,
                status=TransferStatus.VERIFIED,
            ))
        db.commit()
    print("✓ Demo data seeded.")


if __name__ == "__main__":
    main()
