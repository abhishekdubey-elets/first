"""Raw discovered article — output of the Discovery + Extraction agents."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ArticleStatus


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identity / discovery
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(1024))
    source_name: Mapped[str | None] = mapped_column(String(255), index=True)
    publication: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(16), default="en")
    discovery_query: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Extraction
    full_text: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list | None] = mapped_column(JSONB, default=list)
    pdf_links: Mapped[list | None] = mapped_column(JSONB, default=list)
    gov_order_links: Mapped[list | None] = mapped_column(JSONB, default=list)

    # Pipeline state
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(ArticleStatus, name="article_status"),
        default=ArticleStatus.DISCOVERED,
        index=True,
    )
    relevance_score: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transfers = relationship(
        "IasTransfer", back_populates="article", cascade="all, delete-orphan"
    )
