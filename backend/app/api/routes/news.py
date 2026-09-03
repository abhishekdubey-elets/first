"""News Feed routes — discovered/extracted articles, latest first."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, nullslast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user
from app.core.database import get_db
from app.models import Article, IasTransfer
from app.models.enums import ArticleStatus
from app.schemas.common import ArticleOut

router = APIRouter(prefix="/news", tags=["news"])

# Ordering used everywhere the feed is shown: newest publication first, and
# articles without a publication date last (by the time we discovered them).
LATEST_FIRST = (nullslast(Article.published_at.desc()), Article.created_at.desc())


@router.get("")
async def list_news(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
    pg: Pagination = Depends(),
    status: str | None = None,
    q: str | None = Query(None, max_length=200, description="Headline / source search"),
    with_transfers: bool = Query(False, description="Only articles that yielded transfer records"),
    exclude_irrelevant: bool = Query(False, description="Hide articles judged not to be IAS transfer news"),
    days: int | None = Query(None, ge=1, le=365, description="Only the last N days"),
    source: str | None = Query(None, max_length=100),
    language: str | None = Query(None, max_length=8),
):
    # Number of transfer records extracted from each article — the signal that
    # tells a reader which headlines actually produced intelligence.
    transfers_count = (
        select(func.count(IasTransfer.id))
        .where(IasTransfer.article_id == Article.id)
        .correlate(Article)
        .scalar_subquery()
    )

    stmt = select(Article, transfers_count.label("transfers_count"))
    if status:
        stmt = stmt.where(Article.status == status)
    if exclude_irrelevant:
        # Only hide what the pipeline judged NOT to be IAS transfer news. A
        # FAILED article (fetch/LLM error) is still news worth showing.
        stmt = stmt.where(Article.status != ArticleStatus.IRRELEVANT)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Article.title.ilike(like), Article.source_name.ilike(like)))
    if source:
        stmt = stmt.where(Article.source_name.ilike(f"%{source.strip()}%"))
    if language:
        stmt = stmt.where(Article.language == language.strip().lower())
    if with_transfers:
        stmt = stmt.where(transfers_count > 0)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(func.coalesce(Article.published_at, Article.created_at) >= cutoff)

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    rows = (await db.execute(
        stmt.order_by(*LATEST_FIRST).offset(pg.offset).limit(pg.page_size)
    )).all()

    items = []
    for article, n_transfers in rows:
        out = ArticleOut.model_validate(article)
        out.transfers_count = int(n_transfers or 0)
        items.append(out)
    return {"items": items, "total": total, "page": pg.page, "page_size": pg.page_size}
