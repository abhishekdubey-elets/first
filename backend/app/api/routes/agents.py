"""Agent control: trigger a discovery/processing cycle and report its state.

Runs the pipeline as a FastAPI background task (no Celery/Redis). The cycle is
driven on a schedule by the in-process scheduler (see ``app.main``), by an
external cron hitting ``/run-cycle`` with the shared cron token, and on demand
by admins from the UI. Only one cycle runs at a time (``app.workers.tasks``).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.log import SystemLog
from app.workers.tasks import cycle_status, run_discovery_cycle

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status")
async def agent_status(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    """When the discovery cycle last completed, what it produced, and whether
    one is running right now (powers the dashboard's pipeline card)."""
    from app.main import next_scheduled_run

    row = (await db.execute(
        select(SystemLog)
        .where(SystemLog.agent == "orchestrator", SystemLog.action == "run")
        .order_by(SystemLog.created_at.desc())
        .limit(1)
    )).scalars().first()
    state = cycle_status()
    nxt = next_scheduled_run()
    return {
        "last_run": row.created_at.isoformat() if row else None,
        "summary": (row.context if row and row.context else None),
        "interval_seconds": settings.DISCOVERY_INTERVAL_SECONDS,
        "running": bool(state.get("running")),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "trigger": state.get("trigger"),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
        "next_run": nxt.isoformat() if nxt else None,
    }


def _start(background: BackgroundTasks, trigger: str) -> dict:
    if cycle_status().get("running"):
        return {"started": False, "already_running": True}
    background.add_task(run_discovery_cycle, trigger)
    return {"started": True, "already_running": False}


@router.post("/run")
async def run_now(background: BackgroundTasks, _: object = Depends(require_admin)):
    """Kick off an immediate discovery + processing cycle (admin)."""
    return _start(background, "manual")


@router.post("/discover")
async def discover_now(background: BackgroundTasks, _: object = Depends(require_admin)):
    return _start(background, "manual")


@router.post("/run-cycle")
async def run_cycle(
    background: BackgroundTasks,
    x_cron_token: str | None = Header(default=None),
):
    """Scheduled trigger for the discovery cycle (no login — token-protected).

    Point a cron at this, e.g. Supabase pg_cron + pg_net every hour:
        select net.http_post(
          url := '.../api/v1/agents/run-cycle',
          headers := '{"x-cron-token": "<CRON_TOKEN>"}'::jsonb);
    """
    if not settings.CRON_TOKEN or x_cron_token != settings.CRON_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing cron token")
    return _start(background, "cron")
