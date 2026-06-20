"""The structured IAS transfer record — the heart of the system.

Produced by the Information Extraction Agent, refined by the Validation and
Duplicate Detection agents, then exported by the Google Sheets Agent.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import TransferStatus


class IasTransfer(Base):
    __tablename__ = "ias_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Officer identity --------------------------------------------------
    officer_name: Mapped[str] = mapped_column(String(255), index=True)
    ias_batch: Mapped[str | None] = mapped_column(String(32), index=True)
    cadre: Mapped[str | None] = mapped_column(String(64), index=True)
    state: Mapped[str | None] = mapped_column(String(64), index=True)

    # --- Posting movement --------------------------------------------------
    current_designation: Mapped[str | None] = mapped_column(String(512))
    previous_district: Mapped[str | None] = mapped_column(String(255), index=True)
    previous_posting: Mapped[str | None] = mapped_column(String(512))
    new_district: Mapped[str | None] = mapped_column(String(255), index=True)
    new_posting: Mapped[str | None] = mapped_column(String(512))

    # --- Dates -------------------------------------------------------------
    transfer_date: Mapped[str | None] = mapped_column(String(32), index=True)
    effective_date: Mapped[str | None] = mapped_column(String(32))

    # --- Provenance --------------------------------------------------------
    reason: Mapped[str | None] = mapped_column(Text)
    notification_number: Mapped[str | None] = mapped_column(String(255), index=True)
    gov_order_link: Mapped[str | None] = mapped_column(String(2048))
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))

    # --- Trust / dedup -----------------------------------------------------
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    dedup_key: Mapped[str] = mapped_column(String(64), index=True)
    # All source URLs that corroborate this record (validation agent merges).
    corroborating_sources: Mapped[list | None] = mapped_column(JSONB, default=list)
    discrepancies: Mapped[list | None] = mapped_column(JSONB, default=list)
    extracted_by_model: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, name="transfer_status"),
        default=TransferStatus.PENDING,
        index=True,
    )

    # Google Sheets bookkeeping
    sheet_row: Mapped[int | None] = mapped_column(Integer)

    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL")
    )
    article = relationship("Article", back_populates="transfers")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def news_date(self) -> datetime | None:
        """Publication date of the source article (the "news date").

        Surfaced so the UI can fall back to it when the article never states an
        explicit transfer date. Returns None if the article isn't loaded.
        """
        from sqlalchemy import inspect as _sa_inspect

        if "article" in _sa_inspect(self).unloaded:
            return None
        return self.article.published_at if self.article else None
