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
