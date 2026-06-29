"""Agent control: trigger a discovery/processing cycle.

Runs the pipeline as a FastAPI background task (no Celery/Redis). The cycle is
driven on a schedule by an external cron (e.g. Supabase pg_cron) hitting
``/run-cycle`` with the shared cron token, and on demand by admins from the UI.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from app.api.deps import require_admin
from app.core.config import settings
from app.workers.tasks import run_discovery_cycle

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run")
async def run_now(background: BackgroundTasks, _: object = Depends(require_admin)):
    """Kick off an immediate discovery + processing cycle (admin)."""
    background.add_task(run_discovery_cycle)
    return {"started": True}


@router.post("/discover")
async def discover_now(background: BackgroundTasks, _: object = Depends(require_admin)):
    background.add_task(run_discovery_cycle)
    return {"started": True}


@router.post("/run-cycle")
async def run_cycle(
    background: BackgroundTasks,
    x_cron_token: str | None = Header(default=None),
):
    """Scheduled trigger for the discovery cycle (no login — token-protected).

    Point a cron at this, e.g. Supabase pg_cron + pg_net every 10 minutes:
        select net.http_post(
          url := '.../api/v1/agents/run-cycle',
          headers := '{"x-cron-token": "<CRON_TOKEN>"}'::jsonb);
    """
    if not settings.CRON_TOKEN or x_cron_token != settings.CRON_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing cron token")
    background.add_task(run_discovery_cycle)
    return {"started": True}
