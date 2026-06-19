"""Agent control: manually trigger a discovery/processing cycle."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_admin

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run")
async def run_now(_: object = Depends(require_admin)):
    """Kick off an immediate discovery + processing cycle (async via Celery)."""
    from app.workers.tasks import run_discovery_cycle

    task = run_discovery_cycle.delay()
    return {"queued": True, "task_id": task.id}


@router.post("/discover")
async def discover_now(_: object = Depends(require_admin)):
    from app.workers.tasks import run_discovery_cycle

    task = run_discovery_cycle.delay()
    return {"queued": True, "task_id": task.id}
