"""Startup bootstrap: ensure the first admin user exists."""
from __future__ import annotations

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole

log = get_logger(__name__)


async def backfill_source_headlines() -> int:
    """Copy article headlines onto records created before the column existed.

    ``source_headline`` was added so a record keeps its headline after the news
    purge detaches the article. Records extracted earlier have it empty; this
    fills them in from any article still attached. Idempotent and cheap, so it
    runs at every boot — articles age out after the retention window, which is
    exactly when there is nothing left to copy.
    """
    from sqlalchemy import text

    async with AsyncSessionFactory() as db:
        result = await db.execute(text(
            "UPDATE ias_transfers t SET source_headline = a.title "
            "FROM articles a "
            "WHERE t.article_id = a.id "
            "  AND t.source_headline IS NULL AND a.title IS NOT NULL"
        ))
        await db.commit()
    filled = result.rowcount or 0
    if filled:
        log.info("backfilled_source_headlines", count=filled)
    return filled


async def ensure_first_admin() -> None:
    async with AsyncSessionFactory() as db:
        existing = (
            await db.execute(
                select(User).where(User.email == settings.FIRST_ADMIN_EMAIL)
            )
        ).scalar_one_or_none()
        if existing:
            return
        admin = User(
            email=settings.FIRST_ADMIN_EMAIL,
            hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
            full_name="Administrator",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        log.info("created_first_admin", email=settings.FIRST_ADMIN_EMAIL)
