"""Public JSON feed in the CXO Movement Tracker format.

The Elets portal already reads sector feeds shaped like
``cxo-movement-tracker.vercel.app/api/v1/bfsi.json``: a small envelope around a
flat ``records`` array whose objects carry twelve fixed keys. These endpoints
publish the IAS transfer records in exactly that shape, so the portal can read
them through the same code path with only the URL changed.

Each record keeps the twelve CXO keys first and in the same order, then appends
a few IAS-specific ones (state, cadre, batch, government order...). Extra keys
are additive: a consumer written against the CXO format ignores them.

The feed is unauthenticated by default, like the tracker it mirrors — it only
republishes already-public news. Set ``FEED_TOKEN`` to require a shared secret,
or ``PUBLIC_FEED_ENABLED=false`` to switch it off entirely.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models import Article, IasTransfer
from app.models.log import SystemLog
from app.schemas.feed import FeedIndexResponse, FeedRecord, FeedResponse
from app.services.normalize import (
    clean as _clean, norm_batch, parse_loose_date, role_group_of, role_text,
    strip_state_suffix,
)

# A transfer_date this far from the article date is taken to be a mistake
# (an old order quoted in passing, a typo'd year) and the news date is used.
MAX_DAYS_FROM_NEWS = 45

router = APIRouter(tags=["feed"])

API_VERSION = "1"
SOURCE_NAME = "IAS Transfer Intelligence"
SECTOR = "Government"
REGION = "India"

# The twelve keys of the CXO Movement Tracker record, in order. Kept as a
# constant so the tests can assert the contract has not drifted.
CXO_KEYS = (
    "date", "person", "movement", "role", "role_group", "company",
    "moved_from", "moved_from_source", "sector", "region", "headline",
    "source_count",
)

# The response model must declare the twelve keys first and in this order, or
# the portal's CXO-shaped reader breaks. Checked at import so a bad edit fails
# the deployment rather than the consumer.
assert tuple(FeedRecord.model_fields)[: len(CXO_KEYS)] == CXO_KEYS, (
    "FeedRecord must start with the twelve CXO Movement Tracker keys, in order"
)

# Movement is matched in this order: a retirement that also says "transfer"
# is a retirement. "Transfer" is our addition to the tracker's vocabulary
# (Appointment / Resignation / Promotion / Retirement / Re-appointment) because
# it is the core event of this dataset.
_MOVEMENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Retirement", ("retire", "retirement", "superannuat", "सेवानिवृत")),
    ("Resignation", ("resign", "steps down", "step down", "stepped down",
                     "quits", "relieved of", "इस्तीफ")),
    ("Promotion", ("promot", "elevat", "upgrad", "पदोन्नत")),
    ("Re-appointment", ("re-appoint", "reappoint", "extension of", "extended",
                        "tenure extend")),
)


# --- field derivation -------------------------------------------------------
def role_of(t: IasTransfer) -> str:
    return role_text(t.new_posting, t.current_designation, t.new_district)


def record_date(t: IasTransfer) -> str:
    """Best available calendar date for the record, as YYYY-MM-DD.

    A stated transfer date wins, unless it sits implausibly far from when the
    news was published, in which case the publication date is used instead.
    """
    anchor = t.news_date or t.created_at
    for raw in (t.transfer_date, t.effective_date):
        parsed = parse_loose_date(raw)
        if parsed is None:
            continue
        if anchor is not None and abs((parsed.date() - anchor.date()).days) > MAX_DAYS_FROM_NEWS:
            continue
        return parsed.date().isoformat()
    news = t.news_date
    if news is not None:
        return news.date().isoformat()
    return t.created_at.date().isoformat()


def movement_of(t: IasTransfer) -> str:
    blob = " ".join(filter(None, (
        t.reason, t.new_posting, t.current_designation, t.source_headline,
    ))).lower()
    for label, needles in _MOVEMENT_RULES:
        if any(n in blob for n in needles):
            return label
    if _clean(t.previous_district) or _clean(t.previous_posting):
        return "Transfer"
    return "Appointment"


def company_of(t: IasTransfer) -> str:
    """The employing body. IAS officers serve a government, not a company."""
    state, cadre = _clean(t.state), _clean(t.cadre)
    if state and state.upper() != "AGMUT":
        return f"Government of {state}"
    if state or cadre:
        return f"{state or cadre} Cadre"
    return "Government of India"


def headline_of(t: IasTransfer, role: str, movement: str) -> str:
    """The source headline, or a plain sentence when the article has aged out.

    News articles are purged after the retention window while their records are
    kept, so an older record may have no stored headline.
    """
    stored = _clean(t.source_headline)
    if stored:
        return stored
    where = _clean(t.new_district) or _clean(t.state)
    tail = f" in {where}" if where and where.lower() not in role.lower() else ""
    verb = {"Transfer": "transferred as", "Retirement": "retires as",
            "Resignation": "resigns as", "Promotion": "promoted to",
            "Re-appointment": "re-appointed as"}.get(movement, "appointed")
    return f"{t.officer_name} {verb} {role}{tail}".strip()


def to_record(t: IasTransfer) -> dict:
    """One transfer as a CXO-format record plus IAS-specific extras."""
    movement = movement_of(t)
    role = role_of(t)
    moved_from = _clean(t.previous_district) or _clean(t.previous_posting)
    sources = t.corroborating_sources or []

    return {
        # --- the twelve CXO Movement Tracker keys, in order ---
        "date": record_date(t),
        "person": _clean(t.officer_name),
        "movement": movement,
        "role": role,
        "role_group": role_group_of(role),
        "company": company_of(t),
        "moved_from": moved_from,
        "moved_from_source": "article" if moved_from else "",
        "sector": SECTOR,
        "region": REGION,
        "headline": headline_of(t, role, movement),
        "source_count": max(len(sources), 1),
        # --- IAS-specific extras; ignore them for CXO-shaped consumers ---
        "id": t.id,
        "state": _clean(t.state),
        "cadre": _clean(t.cadre),
        "batch": norm_batch(t.ias_batch) or "",
        "district": strip_state_suffix(t.new_district) or "",
        "moved_from_district": strip_state_suffix(t.previous_district) or "",
        "order_number": _clean(t.notification_number),
        "order_link": _clean(t.gov_order_link),
        "source": _clean(t.source_name),
        "source_url": _clean(t.source_url),
        "status": t.status.value if hasattr(t.status, "value") else str(t.status),
        "updated": t.updated_at.isoformat(),
    }


# --- access control ---------------------------------------------------------
async def feed_access(
    token: str | None = Query(None, description="Shared secret, when FEED_TOKEN is set"),
    x_feed_token: str | None = Header(default=None),
) -> None:
    """Open by default; a shared secret only when ``FEED_TOKEN`` is configured."""
    if not settings.PUBLIC_FEED_ENABLED:
        raise HTTPException(status_code=404, detail="Feed is disabled")
    expected = _clean(settings.FEED_TOKEN)
    if expected and (token or x_feed_token) != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing feed token")


# --- data access ------------------------------------------------------------
async def _last_updated(db: AsyncSession) -> str:
    """When the pipeline last completed a cycle, else the newest record."""
    cycle = (await db.execute(
        select(SystemLog.created_at)
        .where(SystemLog.agent == "orchestrator", SystemLog.action == "run")
        .order_by(SystemLog.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if cycle is None:
        cycle = (await db.execute(select(func.max(IasTransfer.updated_at)))).scalar_one_or_none()
    return (cycle or datetime.now(timezone.utc)).isoformat()


async def _records(db: AsyncSession, *, limit: int, days: int | None) -> list[dict]:
    stmt = select(IasTransfer).options(selectinload(IasTransfer.article))
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(IasTransfer.created_at >= cutoff)
    # Order in SQL by the columns we have, then re-sort in Python on the
    # derived calendar date, which can come from free-text fields.
    rows = (await db.execute(
        stmt.order_by(IasTransfer.created_at.desc()).limit(settings.FEED_MAX_RECORDS)
    )).scalars().all()

    records = [to_record(t) for t in rows]
    records.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return records[:limit]


def _envelope(records: list[dict], updated: str) -> dict:
    return {
        "api_version": API_VERSION,
        "source": SOURCE_NAME,
        "sector": SECTOR,
        "updated": updated,
        "count": len(records),
        "records": records,
    }


def _cache(response: Response) -> None:
    # The pipeline runs once a day; a fifteen-minute edge cache is safe.
    response.headers["Cache-Control"] = "public, max-age=900, stale-while-revalidate=3600"
    # Read-only public data, so any site may fetch it from the browser without
    # being added to BACKEND_CORS_ORIGINS. For an origin that IS allowlisted,
    # CORSMiddleware runs after this and replaces the value with that origin.
    if not _clean(settings.FEED_TOKEN):
        response.headers["Access-Control-Allow-Origin"] = "*"


# --- endpoints --------------------------------------------------------------
@router.get(
    "/ias.json",
    response_model=FeedResponse,
    summary="Full IAS transfer feed (CXO Movement Tracker format)",
)
async def ias_feed(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(feed_access),
    limit: int = Query(2000, ge=1, le=10000),
    days: int | None = Query(None, ge=1, le=3650, description="Only the last N days"),
):
    """Every transfer record, newest first, in the CXO Movement Tracker shape."""
    records = await _records(db, limit=limit, days=days)
    _cache(response)
    return _envelope(records, await _last_updated(db))


@router.get(
    "/ias_latest.json",
    response_model=FeedResponse,
    summary="Most recent IAS transfers (CXO Movement Tracker format)",
)
async def ias_latest_feed(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(feed_access),
    limit: int = Query(None, ge=1, le=500),
):
    """The newest slice of the feed, for a homepage block."""
    records = await _records(db, limit=limit or settings.FEED_LATEST_SIZE, days=None)
    _cache(response)
    return _envelope(records, await _last_updated(db))


@router.get("/index.json", response_model=FeedIndexResponse, summary="Feed manifest")
async def feed_index(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(feed_access),
):
    """Counts and the list of available feed endpoints."""
    total = (await db.execute(select(func.count()).select_from(IasTransfer))).scalar_one()
    articles = (await db.execute(select(func.count()).select_from(Article))).scalar_one()
    _cache(response)
    return {
        "api_version": API_VERSION,
        "source": SOURCE_NAME,
        "updated": await _last_updated(db),
        "counts": {
            "ias": total,
            "ias_latest": min(total, settings.FEED_LATEST_SIZE),
            "articles": articles,
        },
        "refresh_interval_seconds": settings.DISCOVERY_INTERVAL_SECONDS,
        "endpoints": ["ias.json", "ias_latest.json", "index.json"],
    }
