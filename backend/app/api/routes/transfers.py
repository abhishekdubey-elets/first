"""Transfer Explorer + Officer Profile routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Pagination, get_current_user
from app.core.database import get_db
from app.models import IasTransfer
from app.schemas.transfer import TransferListOut, TransferOut

router = APIRouter(prefix="/transfers", tags=["transfers"])

_SORT_FIELDS = {
    "created_at": IasTransfer.created_at,
    "transfer_date": IasTransfer.transfer_date,
    "officer": IasTransfer.officer_name,
}


@router.get("", response_model=TransferListOut)
async def list_transfers(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
    pg: Pagination = Depends(),
    q: str | None = None,
    state: str | None = None,
    district: str | None = None,
    officer: str | None = None,
    batch: str | None = None,
    cadre: str | None = None,
    source: str | None = None,
    status: str | None = None,
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    stmt = select(IasTransfer)
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(or_(
            IasTransfer.officer_name.ilike(like),
            IasTransfer.new_posting.ilike(like),
            IasTransfer.previous_posting.ilike(like),
            IasTransfer.new_district.ilike(like),
        ))
    if state:
        conds.append(IasTransfer.state.ilike(f"%{state}%"))
    if district:
        conds.append(or_(
            IasTransfer.new_district.ilike(f"%{district}%"),
            IasTransfer.previous_district.ilike(f"%{district}%"),
        ))
    if officer:
        conds.append(IasTransfer.officer_name.ilike(f"%{officer}%"))
    if batch:
        conds.append(IasTransfer.ias_batch.ilike(f"%{batch}%"))
    if cadre:
        conds.append(IasTransfer.cadre.ilike(f"%{cadre}%"))
    if source:
        conds.append(IasTransfer.source_name.ilike(f"%{source}%"))
    if status:
        conds.append(IasTransfer.status == status)
    if conds:
        stmt = stmt.where(*conds)

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    col = _SORT_FIELDS.get(sort, IasTransfer.created_at)
    col = col.asc() if order == "asc" else col.desc()
    stmt = (
        stmt.options(selectinload(IasTransfer.article))
        .order_by(col)
        .offset(pg.offset)
        .limit(pg.page_size)
    )
    items = (await db.execute(stmt)).scalars().all()

    return TransferListOut(
        items=[TransferOut.model_validate(i) for i in items],
        total=total, page=pg.page, page_size=pg.page_size,
    )


@router.get("/{transfer_id}", response_model=TransferOut)
async def get_transfer(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    rec = (await db.execute(
        select(IasTransfer)
        .where(IasTransfer.id == transfer_id)
        .options(selectinload(IasTransfer.article))
    )).scalars().first()
    if rec is None:
        raise HTTPException(404, "Transfer not found")
    return rec


@router.get("/officer/{name}", response_model=list[TransferOut])
async def officer_history(
    name: str,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    """All transfers for one officer — powers the Officer Profile timeline."""
    rows = (await db.execute(
        select(IasTransfer)
        .where(IasTransfer.officer_name.ilike(f"%{name}%"))
        .options(selectinload(IasTransfer.article))
        .order_by(IasTransfer.created_at.desc())
    )).scalars().all()
    return rows
