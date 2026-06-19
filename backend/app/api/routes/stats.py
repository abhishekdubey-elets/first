"""Dashboard stats + analytics routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import IasTransfer
from app.models.enums import TransferStatus
from app.schemas.common import StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


async def _count(db, *conds) -> int:
    stmt = select(func.count()).select_from(IasTransfer)
    if conds:
        stmt = stmt.where(*conds)
    return (await db.execute(stmt)).scalar_one()


@router.get("", response_model=StatsOut)
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    by_state_rows = (await db.execute(
        select(IasTransfer.state, func.count())
        .group_by(IasTransfer.state)
        .order_by(func.count().desc())
        .limit(15)
    )).all()

    buckets = {"0.0-0.5": 0, "0.5-0.7": 0, "0.7-0.85": 0, "0.85-1.0": 0}
    conf_rows = (await db.execute(select(IasTransfer.confidence_score))).scalars().all()
    for c in conf_rows:
        if c < 0.5:
            buckets["0.0-0.5"] += 1
        elif c < 0.7:
            buckets["0.5-0.7"] += 1
        elif c < 0.85:
            buckets["0.7-0.85"] += 1
        else:
            buckets["0.85-1.0"] += 1

    avg = (await db.execute(select(func.avg(IasTransfer.confidence_score)))).scalar()

    return StatsOut(
        total_transfers=await _count(db),
        today=await _count(db, IasTransfer.created_at >= today),
        this_week=await _count(db, IasTransfer.created_at >= week),
        this_month=await _count(db, IasTransfer.created_at >= month),
        pending=await _count(db, IasTransfer.status == TransferStatus.PENDING),
        verified=await _count(db, IasTransfer.status == TransferStatus.VERIFIED),
        exported=await _count(db, IasTransfer.status == TransferStatus.EXPORTED),
        avg_confidence=round(float(avg or 0), 3),
        by_state=[{"state": s or "Unknown", "count": n} for s, n in by_state_rows],
        confidence_distribution=[{"bucket": k, "count": v} for k, v in buckets.items()],
    )


@router.get("/analytics")
async def analytics(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    """Series for the Analytics page charts."""
    by_state = (await db.execute(
        select(IasTransfer.state, func.count())
        .group_by(IasTransfer.state).order_by(func.count().desc()).limit(20)
    )).all()
    by_cadre = (await db.execute(
        select(IasTransfer.cadre, func.count())
        .group_by(IasTransfer.cadre).order_by(func.count().desc()).limit(15)
    )).all()
    by_district = (await db.execute(
        select(IasTransfer.new_district, func.count())
        .group_by(IasTransfer.new_district).order_by(func.count().desc()).limit(20)
    )).all()
    by_month = (await db.execute(
        select(
            func.to_char(func.date_trunc("month", IasTransfer.created_at), "YYYY-MM"),
            func.count(),
        ).group_by(func.date_trunc("month", IasTransfer.created_at))
        .order_by(func.date_trunc("month", IasTransfer.created_at))
    )).all()

    return {
        "by_state": [{"state": s or "Unknown", "count": n} for s, n in by_state],
        "by_cadre": [{"cadre": c or "Unknown", "count": n} for c, n in by_cadre],
        "by_district": [{"district": d or "Unknown", "count": n} for d, n in by_district],
        "by_month": [{"month": m, "count": n} for m, n in by_month],
    }
