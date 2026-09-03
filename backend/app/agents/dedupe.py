"""Duplicate Detection + Validation Agent.

Given a freshly extracted transfer, computes a stable dedup key and decides
whether to insert a new record or merge into an existing one. When multiple
sources report the same transfer it merges them, raises confidence, and flags
field discrepancies.
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.core.config import settings
from app.models.enums import TransferStatus
from app.models.transfer import IasTransfer
from app.schemas.transfer import ExtractedTransfer

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(value: str | None) -> str:
    return _NON_ALNUM.sub("", (value or "").lower())


def compute_dedup_key(t: ExtractedTransfer | IasTransfer) -> str:
    """Stable key from officer + (gov order number OR new posting + date).

    Matches the spec's dedup signals: Officer Name, Transfer Date, Government
    Order Number, plus the destination posting so two unrelated transfers of the
    same officer don't collapse.
    """
    officer = _norm(getattr(t, "officer_name", None))
    gov = _norm(getattr(t, "notification_number", None))
    dest = _norm(getattr(t, "new_district", None)) or _norm(getattr(t, "new_posting", None))
    date = _norm(getattr(t, "transfer_date", None)) or _norm(getattr(t, "effective_date", None))
    basis = f"{officer}|{gov}" if gov else f"{officer}|{dest}|{date}"
    return hashlib.sha256(basis.encode()).hexdigest()[:32]


_MERGE_FIELDS = (
    "ias_batch", "cadre", "state", "current_designation", "previous_district",
    "previous_posting", "new_district", "new_posting", "transfer_date",
    "effective_date", "reason", "notification_number", "gov_order_link",
)


class DedupeAgent(BaseAgent):
    name = "dedupe"

    def upsert(self, extracted: ExtractedTransfer, *, article, model: str) -> tuple[IasTransfer, bool]:
        """Insert or merge. Returns (record, created)."""
        key = compute_dedup_key(extracted)
        existing = self.db.execute(
            select(IasTransfer).where(IasTransfer.dedup_key == key)
        ).scalars().first()

        if existing is None:
            record = self._create(extracted, key, article, model)
            self.db.add(record)
            self.db.flush()
            self.audit("dedupe", f"New transfer: {record.officer_name}",
                       transfer_id=record.id, key=key)
            return record, True

        created = False
        self._merge(existing, extracted, article)
        self.audit("dedupe", f"Merged duplicate into transfer {existing.id}",
                   transfer_id=existing.id, key=key,
                   sources=len(existing.corroborating_sources or []))
        return existing, created

    # --- helpers -----------------------------------------------------------
    def _create(self, e: ExtractedTransfer, key: str, article, model: str) -> IasTransfer:
        return IasTransfer(
            officer_name=e.officer_name.strip(),
            ias_batch=e.ias_batch,
            cadre=e.cadre,
            state=e.state,
            current_designation=e.current_designation,
            previous_district=e.previous_district,
            previous_posting=e.previous_posting,
            new_district=e.new_district,
            new_posting=e.new_posting,
            transfer_date=e.transfer_date,
            effective_date=e.effective_date,
            reason=e.reason,
            notification_number=e.notification_number,
            gov_order_link=e.gov_order_link,
            source_name=article.source_name,
            source_url=getattr(article, "resolved_url", None) or article.url,
            source_headline=(getattr(article, "title", None) or None),
            confidence_score=e.confidence_score,
            dedup_key=key,
            corroborating_sources=[article.url] if article.url else [],
            discrepancies=[],
            extracted_by_model=model,
            article_id=article.id,
            status=TransferStatus.PENDING,
        )

    def _merge(self, rec: IasTransfer, e: ExtractedTransfer, article) -> None:
        """Validation: corroborate from a new source, fill gaps, flag conflicts."""
        sources = list(rec.corroborating_sources or [])
        new_source = getattr(article, "resolved_url", None) or article.url
        is_new_source = new_source and new_source not in sources

        discrepancies = list(rec.discrepancies or [])
        for field in _MERGE_FIELDS:
            new_val = getattr(e, field)
            cur_val = getattr(rec, field)
            if not new_val:
                continue
            if not cur_val:
                setattr(rec, field, new_val)  # fill a gap
            elif _norm(str(cur_val)) != _norm(str(new_val)):
                discrepancies.append({
                    "field": field, "existing": cur_val, "incoming": new_val,
                    "source": new_source,
                })

        if is_new_source:
            sources.append(new_source)
            # Multiple independent sources → boost confidence toward 1.0.
            boost = min(0.12 * (len(sources) - 1), 0.3)
            rec.confidence_score = round(min(1.0, max(rec.confidence_score, e.confidence_score) + boost), 3)

        if not rec.source_headline and getattr(article, "title", None):
            rec.source_headline = article.title

        rec.corroborating_sources = sources
        rec.discrepancies = discrepancies

        # Status: conflicted if sources disagree, else verified once corroborated
        # or already high confidence.
        if discrepancies:
            rec.status = TransferStatus.CONFLICTED
        elif len(sources) >= 2 or rec.confidence_score >= settings.HIGH_CONFIDENCE_THRESHOLD:
            if rec.status in (TransferStatus.PENDING, TransferStatus.CONFLICTED):
                rec.status = TransferStatus.VERIFIED
