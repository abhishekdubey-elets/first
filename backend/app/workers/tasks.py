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

import re
import threading
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import selectinload

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
    """Web-search to fill gaps (batch/cadre/state/from/to/date) on records missing them.

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
                    IasTransfer.ias_batch.is_(None),
                    IasTransfer.cadre.is_(None),
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


# --- data-quality passes -------------------------------------------------------
# These run every cycle, after extraction and before enrichment, so the web
# search is not spent on records that are about to be merged or filled from a
# sibling. All are idempotent and cheap (a few thousand rows, no network).

_PROPAGATED_FIELDS = ("ias_batch", "cadre", "state")
_MERGE_FILL_FIELDS = (
    "ias_batch", "cadre", "state", "current_designation", "previous_district",
    "previous_posting", "new_district", "new_posting", "transfer_date",
    "effective_date", "reason", "notification_number", "gov_order_link",
    "source_headline",
)


def normalize_existing_records() -> dict:
    """Apply the shared normalisers to rows extracted before they existed.

    Batches become four-digit years, districts lose a trailing ", State", and
    links that only looked like government orders because of a substring match
    ("border" contains "order") are cleared.
    """
    from app.core.india import canonical_state
    from app.services.normalize import looks_like_gov_order, norm_batch, strip_state_suffix

    changed = 0
    with session_scope() as db:
        for r in db.execute(select(IasTransfer)).scalars():
            if r.ias_batch:
                nb = norm_batch(r.ias_batch)
                if nb != r.ias_batch:
                    r.ias_batch = nb; changed += 1
            for fld in ("new_district", "previous_district"):
                v = getattr(r, fld)
                if v:
                    s = strip_state_suffix(v)
                    if s and canonical_state(s):
                        s = None
                        if not r.state:
                            r.state = canonical_state(v.split(",")[-1].strip()) or r.state
                    if s != v:
                        setattr(r, fld, s); changed += 1
            if r.gov_order_link and not looks_like_gov_order(r.gov_order_link):
                r.gov_order_link = None; changed += 1
        db.commit()
    if changed:
        log.info("normalized_existing_records", changes=changed)
    return {"changes": changed}


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_TEXT_FIELDS = (
    "officer_name", "current_designation", "previous_district", "previous_posting",
    "new_district", "new_posting", "reason", "cadre",
)
_ROMANIZE_SYSTEM = (
    "You convert Indian civil-service transfer records from Hindi to English. For "
    "each record, transliterate personal names the way Indian English newspapers "
    "do and translate designations, departments and place names. Keep values that "
    "are already English unchanged. Return strict JSON: an object with key "
    "'records', a list in the same order, each with the same keys as the input."
)


def needs_romanization(r: IasTransfer) -> bool:
    return any(_DEVANAGARI.search(getattr(r, f) or "") for f in _TEXT_FIELDS)


def romanize_hindi_records(limit: int | None = None) -> dict:
    """Translate Hindi-script fields on older records to English.

    The extraction prompt now asks for English output, so this only touches
    records from before that rule and the occasional slip. It exists because
    one officer reported in Hindi and English would otherwise be two records
    that no name matching can join. Batched, so it costs one LLM call per ten
    records, and bounded per cycle.
    """
    from app.services import llm
    from app.services.normalize import clean

    limit = limit or settings.ENRICHMENT_BATCH_SIZE
    changed = 0
    with session_scope() as db:
        rows = [r for r in db.execute(
            select(IasTransfer).order_by(IasTransfer.created_at.desc())
        ).scalars() if needs_romanization(r)][:limit]
        for i in range(0, len(rows), 10):
            batch = rows[i : i + 10]
            payload = [{f: getattr(r, f) or "" for f in _TEXT_FIELDS} for r in batch]
            try:
                out = llm.complete_json(_ROMANIZE_SYSTEM,
                                        "Records:\n" + __import__("json").dumps(payload, ensure_ascii=False))
                results = out.get("records") if isinstance(out, dict) else None
            except Exception as exc:  # noqa: BLE001
                log.warning("romanize_batch_failed", error=str(exc)[:200])
                continue
            if not isinstance(results, list) or len(results) != len(batch):
                continue
            for r, res in zip(batch, results):
                if not isinstance(res, dict):
                    continue
                for f in _TEXT_FIELDS:
                    new = clean(res.get(f))
                    if new and new != (getattr(r, f) or "") and not _DEVANAGARI.search(new):
                        setattr(r, f, new)
                        changed += 1
        db.commit()
    if changed:
        log.info("romanized_hindi_records", fields=changed)
    return {"fields": changed, "records": len(rows)}


def _record_day(r: IasTransfer):
    from app.services.normalize import parse_loose_date

    parsed = parse_loose_date(r.transfer_date) or parse_loose_date(r.effective_date)
    if parsed is not None:
        return parsed.date()
    nd = r.news_date
    return (nd or r.created_at).date()


def _same_movement(a: IasTransfer, b: IasTransfer, window_days: int) -> bool:
    """Two records describe one event: same role group, close in time.

    For the catch-all "Other" group the destination posting itself must match,
    so two unrelated "Other" posts are never folded together.
    """
    from app.services.normalize import norm_name, role_group_of, role_text

    ra = role_text(a.new_posting, a.current_designation, a.new_district)
    rb = role_text(b.new_posting, b.current_designation, b.new_district)
    ga, gb = role_group_of(ra), role_group_of(rb)
    if ga != gb:
        return False
    if ga == "Other" and norm_name(ra) != norm_name(rb):
        return False
    return abs((_record_day(a) - _record_day(b)).days) <= window_days


def _absorb(target: IasTransfer, dup: IasTransfer) -> None:
    """Fold ``dup`` into ``target``: fill gaps, union sources, flag conflicts."""
    from app.agents.dedupe import _norm
    from app.models.enums import TransferStatus

    discrepancies = list(target.discrepancies or [])
    for fld in _MERGE_FILL_FIELDS:
        cur, new = getattr(target, fld), getattr(dup, fld)
        if not new:
            continue
        if not cur:
            setattr(target, fld, new)
        elif fld not in ("source_headline", "reason") and _norm(str(cur)) != _norm(str(new)):
            discrepancies.append({"field": fld, "existing": cur, "incoming": new,
                                  "source": dup.source_url})
    sources = list(target.corroborating_sources or [])
    for s in (dup.corroborating_sources or []) + [dup.source_url]:
        if s and s not in sources:
            sources.append(s)
    target.corroborating_sources = sources
    target.discrepancies = discrepancies
    target.confidence_score = round(max(target.confidence_score, dup.confidence_score), 3)
    if discrepancies:
        target.status = TransferStatus.CONFLICTED
    elif len(sources) >= 2 and target.status == TransferStatus.PENDING:
        target.status = TransferStatus.VERIFIED


def merge_near_duplicates(window_days: int = 10) -> dict:
    """Collapse records that describe the same movement of the same officer.

    The dedupe key is exact ("Chief Secretary, Manipur" and "Chief Secretary"
    are different strings), so a reshuffle reported by several outlets can
    leave two or three records for one appointment. Records for the same
    officer, in the same role group, dated within ``window_days`` of each other
    are merged into the earliest one; the later rows are deleted.
    """
    from app.services.normalize import norm_name

    merged = 0
    with session_scope() as db:
        rows = db.execute(
            select(IasTransfer).options(selectinload(IasTransfer.article))
            .order_by(IasTransfer.created_at.asc(), IasTransfer.id.asc())
        ).scalars().all()
        groups: dict[str, list[IasTransfer]] = defaultdict(list)
        for r in rows:
            groups[norm_name(r.officer_name)].append(r)
        for recs in groups.values():
            if len(recs) < 2:
                continue
            kept: list[IasTransfer] = []
            for r in recs:
                target = next((k for k in kept if _same_movement(k, r, window_days)), None)
                if target is None:
                    kept.append(r)
                    continue
                _absorb(target, r)
                db.delete(r)
                merged += 1
        db.commit()
    if merged:
        log.info("merged_near_duplicates", merged=merged)
    return {"merged": merged}


def propagate_officer_facts() -> dict:
    """Copy stable facts (batch, cadre, state) between records of one officer.

    An officer's batch does not change between postings, so once any record
    knows it every record can. Free, no LLM, no network.
    """
    from app.services.normalize import norm_name

    filled = 0
    with session_scope() as db:
        rows = db.execute(select(IasTransfer)).scalars().all()
        groups: dict[str, list[IasTransfer]] = defaultdict(list)
        for r in rows:
            groups[norm_name(r.officer_name)].append(r)
        for recs in groups.values():
            if len(recs) < 2:
                continue
            for fld in _PROPAGATED_FIELDS:
                values = [getattr(r, fld) for r in recs if getattr(r, fld)]
                if not values:
                    continue
                best = Counter(values).most_common(1)[0][0]
                for r in recs:
                    if not getattr(r, fld):
                        setattr(r, fld, best); filled += 1
        db.commit()
    if filled:
        log.info("propagated_officer_facts", filled=filled)
    return {"filled": filled}


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
    for key, step in (("normalized", normalize_existing_records),
                      ("romanized", romanize_hindi_records),
                      ("merged", merge_near_duplicates),
                      ("propagated", propagate_officer_facts)):
        try:
            result[key] = step()
        except Exception as exc:  # noqa: BLE001 — quality passes never break the cycle
            log.warning(f"{key}_failed", error=str(exc))
            result[key] = {"error": str(exc)[:300]}
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
