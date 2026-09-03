"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    agents, auth, chat, feed, news, settings as settings_route, stats, sync, transfers,
)
from app.bootstrap import backfill_source_headlines, ensure_first_admin
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

# Startup diagnostics surfaced by /health so a mis-configured deployment (bad
# DB password, unreachable host, ...) is visible from the outside instead of
# leaving the container in a crash loop with no logs.
_startup: dict = {"db_ok": None, "db_error": None, "schema_ok": None,
                  "admin_ok": None, "scheduler": None, "started_at": None}
_scheduler = None


def _start_inprocess_scheduler():
    """Drive the discovery cycle on a background thread (no Celery / no cron).

    Single-container hosts (Hugging Face Spaces) run only the API process, so
    there is no worker/beat and no guarantee an external cron exists. This runs
    the same in-process ``run_discovery_cycle`` on the configured cadence, plus
    once shortly after boot so the dashboard catches up immediately. Returns the
    scheduler (for clean shutdown) or ``None`` if disabled/unavailable.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception as exc:  # noqa: BLE001
        log.warning("scheduler_unavailable", error=str(exc))
        return None

    from app.workers.tasks import run_discovery_cycle

    interval = max(60, int(settings.DISCOVERY_INTERVAL_SECONDS))
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_discovery_cycle, "interval", seconds=interval,
        kwargs={"trigger": "scheduler"},
        id="discovery", max_instances=1, coalesce=True, misfire_grace_time=600,
    )
    scheduler.add_job(run_discovery_cycle, "date", id="discovery_boot",
                      kwargs={"trigger": "boot"})
    scheduler.start()
    log.info("inprocess_scheduler_started", interval_seconds=interval)
    return scheduler


def next_scheduled_run() -> datetime | None:
    """When the in-process scheduler will next fire the discovery job."""
    if _scheduler is None:
        return None
    try:
        job = _scheduler.get_job("discovery")
        return job.next_run_time if job else None
    except Exception:  # noqa: BLE001
        return None


def _materialize_google_credentials() -> None:
    """Write the service-account JSON from an env secret to disk on boot.

    Hugging Face Spaces have an ephemeral filesystem, so credentials uploaded via
    the Settings page are wiped on every restart. Providing the JSON as the
    ``GOOGLE_CREDENTIALS_JSON`` secret makes Sheets export survive restarts: we
    just write it to ``GOOGLE_CREDENTIALS_FILE`` (only if not already present).
    """
    raw = (settings.GOOGLE_CREDENTIALS_JSON or "").strip()
    if not raw:
        return
    import json as _json
    from pathlib import Path

    try:
        _json.loads(raw)  # validate
        path = Path(settings.GOOGLE_CREDENTIALS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        log.info("google_credentials_materialized", path=str(path))
    except Exception as exc:  # noqa: BLE001
        log.warning("google_credentials_materialize_failed", error=str(exc))


async def _prepare_database() -> None:
    """Check connectivity, ensure schema, ensure the first admin — never crash.

    A database problem is recorded in ``_startup`` (reported by ``/health``)
    rather than aborting startup: an API that answers ``/health`` with a clear
    error is far easier to fix than a container stuck in RUNTIME_ERROR.
    """
    from app.core.database import check_connection, ensure_schema

    ok, err = await asyncio.to_thread(check_connection)
    _startup["db_ok"], _startup["db_error"] = ok, err
    if not ok:
        log.error("database_unreachable", error=err)
        return
    try:
        await asyncio.to_thread(ensure_schema)
        _startup["schema_ok"] = True
    except Exception as exc:  # noqa: BLE001
        _startup["schema_ok"] = False
        log.error("ensure_schema_failed", error=str(exc))
    try:
        await ensure_first_admin()
        _startup["admin_ok"] = True
    except Exception as exc:  # noqa: BLE001
        _startup["admin_ok"] = False
        log.error("ensure_first_admin_failed", error=str(exc))
    try:
        await backfill_source_headlines()
    except Exception as exc:  # noqa: BLE001 — cosmetic, never block startup
        log.warning("backfill_source_headlines_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    log.info("starting_up", env=settings.ENVIRONMENT, version=__version__)
    _startup["started_at"] = datetime.now(timezone.utc).isoformat()
    _materialize_google_credentials()
    await _prepare_database()
    if settings.ENABLE_INPROCESS_SCHEDULER:
        _scheduler = _start_inprocess_scheduler()
        _startup["scheduler"] = "running" if _scheduler else "unavailable"
    else:
        _startup["scheduler"] = "disabled"
    yield
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
    log.info("shutting_down")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=__version__,
    description=(
        "Autonomous multi-agent system that monitors the internet for IAS "
        "officer transfer news, extracts structured records, and syncs them to "
        "Google Sheets and an interactive dashboard."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled_exception", path=request.url.path)
    # Responses produced here bypass CORSMiddleware, so the browser would report
    # a CORS failure instead of the real 500. Echo the allowed origin manually.
    headers = {}
    origin = request.headers.get("origin")
    if origin and (origin in settings.cors_origins or "*" in settings.cors_origins):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(status_code=500, content={"detail": "Internal server error"}, headers=headers)


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness, database probe, scheduler and last-crawl summary",
    responses={200: {"content": {"application/json": {"example": {
        "status": "ok",
        "version": "0.1.0",
        "database": {"ok": True, "error": None},
        "scheduler": {"enabled": True, "interval_seconds": 86400,
                      "next_run": "2026-09-04T07:05:48+00:00"},
        "llm": {"provider": "anthropic", "model": "claude-opus-5", "configured": True},
        "pipeline": {"running": False, "last_error": None,
                     "last_cycle": {"articles": 180, "transfers": 13, "new": 8,
                                    "failed": 3, "remaining": 0}},
    }}}}},
)
async def health():
    """Liveness + a live database probe.

    ``status`` is ``ok`` when the database answers, ``degraded`` otherwise (the
    process stays up so the error is visible here and in the dashboard).
    """
    from app.core.database import check_connection
    from app.services import llm
    from app.workers.tasks import cycle_status

    ok, err = await asyncio.to_thread(check_connection)
    nxt = next_scheduled_run()
    state = cycle_status()
    processed = (state.get("last_result") or {}).get("processed") or {}
    return {
        "status": "ok" if ok else "degraded",
        "version": __version__,
        "database": {"ok": ok, "error": err},
        "startup": _startup,
        "scheduler": {
            "enabled": settings.ENABLE_INPROCESS_SCHEDULER,
            "interval_seconds": settings.DISCOVERY_INTERVAL_SECONDS,
            "next_run": nxt.isoformat() if nxt else None,
        },
        # Unauthenticated, non-sensitive view of the pipeline so a deployment
        # can be verified from the outside (no record content is exposed).
        "llm": {"provider": llm.active_provider(), "model": llm.active_model(),
                "configured": llm.is_available()},
        "pipeline": {
            "running": bool(state.get("running")),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "last_error": state.get("last_error"),
            "last_cycle": {k: processed.get(k) for k in
                           ("articles", "transfers", "new", "failed", "remaining")},
        },
    }


api = settings.API_V1_PREFIX
for module in (auth, transfers, stats, news, sync, settings_route, agents, chat, feed):
    app.include_router(module.router, prefix=api)
