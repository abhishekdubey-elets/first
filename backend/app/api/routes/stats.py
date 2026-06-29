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

    return StatsOut(
        total_transfers=await _count(db),
        today=await _count(db, IasTransfer.created_at >= today),
        this_week=await _count(db, IasTransfer.created_at >= week),
        this_month=await _count(db, IasTransfer.created_at >= month),
        pending=await _count(db, IasTransfer.status == TransferStatus.PENDING),
        verified=await _count(db, IasTransfer.status == TransferStatus.VERIFIED),
        exported=await _count(db, IasTransfer.status == TransferStatus.EXPORTED),
        by_state=[{"state": s or "Unknown", "count": n} for s, n in by_state_rows],
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
        .where(IasTransfer.new_district.is_not(None))
        .group_by(IasTransfer.new_district).order_by(func.count().desc()).limit(20)
    )).all()
    # Group/order by the SAME expression used in SELECT. Postgres can't match a
    # bare date_trunc() in GROUP BY to a to_char(date_trunc()) in SELECT when the
    # truncation unit is a bound parameter, so reuse one expression object.
    month_expr = func.to_char(
        func.date_trunc("month", IasTransfer.created_at), "YYYY-MM"
    )
    by_month = (await db.execute(
        select(month_expr, func.count())
        .group_by(month_expr)
        .order_by(month_expr)
    )).all()

    return {
        "by_state": [{"state": s or "Unknown", "count": n} for s, n in by_state],
        "by_cadre": [{"cadre": c or "Unknown", "count": n} for c, n in by_cadre],
        "by_district": [{"district": d, "count": n} for d, n in by_district],
        "by_month": [{"month": m, "count": n} for m, n in by_month],
    }
