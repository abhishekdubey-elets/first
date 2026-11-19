"""What the Officer Research Agent found about one officer.

Officers are not stored as rows (profiles are built from transfer records), so
research is filed under ``officer_key``: the officer's name key plus home
state, e.g. ``anitasharma|uttar-pradesh``. A profile picks up every research
row whose name key and state match it, so a row survives an officer's profile
id changing.

Images are stored as links to where they were published, with the page and
caption that name the officer. Nothing is downloaded or re-hosted.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OfficerResearch(Base):
    __tablename__ = "officer_research"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    officer_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name_key: Mapped[str] = mapped_column(String(160), index=True)
    state: Mapped[str | None] = mapped_column(String(64))
    officer_id: Mapped[str | None] = mapped_column(String(255))
    officer_name: Mapped[str] = mapped_column(String(255))

    # queued (an admin asked for it) | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)

    # [{url, title, source, published, snippet, verdict}]
    press: Mapped[list | None] = mapped_column(JSONB, default=list)
    # [{image_url, page_url, caption, source, origin, hidden}]
    images: Mapped[list | None] = mapped_column(JSONB, default=list)
    # {title, url, extract, image_url, image_page} or null
    wikipedia: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
