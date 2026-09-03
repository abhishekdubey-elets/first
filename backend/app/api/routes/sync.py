"""Google Sheets Sync page: status, manual export, retry failed."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models import IasTransfer, SheetSyncLog
from app.models.enums import TransferStatus
from app.schemas.common import SyncLogOut

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/logs", response_model=list[SyncLogOut])
async def sync_logs(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    rows = (await db.execute(
        select(SheetSyncLog).order_by(SheetSyncLog.created_at.desc()).limit(50)
    )).scalars().all()
    return rows


@router.get("/status")
async def sync_status(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    from app.services.google_sheets import sheet_health

    last = (await db.execute(
        select(SheetSyncLog).order_by(SheetSyncLog.created_at.desc()).limit(1)
    )).scalars().first()
    failed = (await db.execute(
        select(func.count()).select_from(IasTransfer)
        .where(IasTransfer.status == TransferStatus.EXPORT_FAILED)
    )).scalar_one()
    exported = (await db.execute(
        select(func.count()).select_from(IasTransfer)
        .where(IasTransfer.status == TransferStatus.EXPORTED)
    )).scalar_one()

    return {
        "last_sync": last.created_at.isoformat() if last else None,
        "last_status": last.status.value if last else None,
        "exported_rows": exported,
        "failed_uploads": failed,
        # gspread is synchronous (several HTTPS round-trips): keep it off the loop.
        "sheet": await asyncio.to_thread(sheet_health),
    }


@router.post("/retry")
async def retry_failed(
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Re-run the Sheets export for every failed/verified record.

    Records keep their EXPORT_FAILED status until the export actually
    succeeds, so the failure count stays truthful if the retry fails too.
    """
    failed = (await db.execute(
        select(func.count()).select_from(IasTransfer)
        .where(IasTransfer.status == TransferStatus.EXPORT_FAILED)
    )).scalar_one()
    # Run a dedicated Sheets export pass in the background (no Celery).
    from app.workers.tasks import export_verified

    background.add_task(export_verified)
    return {"requeued": failed}
