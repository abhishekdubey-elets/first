"""System Logs + Sheets Sync routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user
from app.core.database import get_db
from app.models import SheetSyncLog, SystemLog
from app.schemas.common import LogOut, SyncLogOut

router = APIRouter(tags=["logs"])


@router.get("/logs")
async def list_logs(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
    pg: Pagination = Depends(),
    level: str | None = None,
    agent: str | None = None,
    q: str | None = None,
):
    stmt = select(SystemLog)
    conds = []
    if level:
        conds.append(SystemLog.level == level)
    if agent:
        conds.append(SystemLog.agent == agent)
    if q:
        conds.append(or_(
            SystemLog.message.ilike(f"%{q}%"),
            SystemLog.action.ilike(f"%{q}%"),
        ))
    if conds:
        stmt = stmt.where(*conds)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    rows = (await db.execute(
        stmt.order_by(SystemLog.created_at.desc()).offset(pg.offset).limit(pg.page_size)
    )).scalars().all()
    return {
        "items": [LogOut.model_validate(r) for r in rows],
        "total": total, "page": pg.page, "page_size": pg.page_size,
    }


@router.get("/sync/logs", response_model=list[SyncLogOut])
async def sync_logs(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    rows = (await db.execute(
        select(SheetSyncLog).order_by(SheetSyncLog.created_at.desc()).limit(50)
    )).scalars().all()
    return rows
