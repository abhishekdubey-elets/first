"""System log + Google Sheets sync log (audit trail surfaced in the dashboard)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import LogLevel, SyncStatus


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, name="log_level"), default=LogLevel.INFO, index=True
    )
    agent: Mapped[str | None] = mapped_column(String(64), index=True)
    action: Mapped[str | None] = mapped_column(String(128), index=True)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class SheetSyncLog(Base):
    __tablename__ = "sheet_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status"), index=True
    )
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
