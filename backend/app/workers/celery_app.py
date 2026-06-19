"""Celery application + beat schedule.

The Discovery Agent runs every ``DISCOVERY_INTERVAL_SECONDS`` (default 10 min)
via Celery beat, which enqueues a discovery task; that task then fans out the
per-article processing pipeline.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery = Celery(
    "ias_transfers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.TASK_TIMEOUT_SECONDS,
    task_soft_time_limit=settings.TASK_TIMEOUT_SECONDS - 60,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=30,
    task_max_retries=settings.MAX_RETRIES,
)

# Make this the default app so `.delay()` from the FastAPI process routes to this
# Redis broker rather than Celery's amqp:// default.
celery.set_default()

celery.conf.beat_schedule = {
    "discover-transfers": {
        "task": "app.workers.tasks.run_discovery_cycle",
        "schedule": float(settings.DISCOVERY_INTERVAL_SECONDS),
    },
}
