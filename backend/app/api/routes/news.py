"""News Feed routes — discovered/extracted articles."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user
from app.core.database import get_db
from app.models import Article
from app.schemas.common import ArticleOut

router = APIRouter(prefix="/news", tags=["news"])


@router.get("")
async def list_news(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
    pg: Pagination = Depends(),
    status: str | None = None,
):
    stmt = select(Article)
    if status:
        stmt = stmt.where(Article.status == status)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    # Latest news first: by the article's publication date (newest), with
    # articles lacking one ordered last by discovery time.
    rows = (await db.execute(
        stmt.order_by(
            nullslast(Article.published_at.desc()),
            Article.created_at.desc(),
        ).offset(pg.offset).limit(pg.page_size)
    )).scalars().all()
    return {
        "items": [ArticleOut.model_validate(r) for r in rows],
        "total": total, "page": pg.page, "page_size": pg.page_size,
    }
