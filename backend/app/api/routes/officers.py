"""Officer directory + profile: a page for every officer we have seen moved.

Profiles are assembled from the transfer records on each request (see
``app.services.officers``); there is no separate officers table to keep in
sync, so a profile is always as current as the last pipeline cycle. What the
Officer Research Agent found (press, photos, Wikipedia) is attached from the
``officer_research`` table.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Pagination, get_current_user, require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models import IasTransfer, OfficerResearch, User
from app.schemas.officer import (
    ImageVisibility,
    OfficerListOut,
    OfficerProfile,
    OfficerResearchOut,
    OfficerSummary,
)
from app.services import officers as svc

router = APIRouter(prefix="/officers", tags=["officers"])


async def _load_officers(db: AsyncSession) -> list[svc.Officer]:
    rows = (await db.execute(
        select(IasTransfer)
        .options(selectinload(IasTransfer.article))
        .order_by(IasTransfer.created_at.desc(), IasTransfer.id.desc())
        .limit(settings.FEED_MAX_RECORDS)
    )).scalars().all()
    return svc.build_officers(rows)


async def _research_rows(db: AsyncSession) -> list[OfficerResearch]:
    return list((await db.execute(select(OfficerResearch))).scalars().all())


async def _find(db: AsyncSession, officer_id: str):
    officers = await _load_officers(db)
    officer, alternates = svc.resolve(officers, officer_id)
    if officer is None:
        raise HTTPException(404, "Officer not found")
    return officer, alternates, officers


@router.get("", response_model=OfficerListOut, summary="Directory of transferred officers")
async def list_officers(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
    pg: Pagination = Depends(),
    q: str | None = Query(None, description="Name or spelling variant (substring)"),
    state: str | None = Query(None, description="Any state the officer has served in"),
    batch: str | None = Query(None, description="IAS batch year, e.g. 2009"),
    cadre: str | None = None,
    sort: str = Query("recent", pattern=f"^({'|'.join(svc.SORT_NAMES)})$"),
    order: str | None = Query(None, pattern="^(asc|desc)$",
                              description="Defaults to desc, or asc for sort=name"),
):
    """Every officer with at least one transfer record, most recently moved first."""
    found = svc.directory(
        await _load_officers(db), q=q, state=state, batch=batch, cadre=cadre,
        sort=sort, order=order,
    )
    page = found[pg.offset: pg.offset + pg.page_size]
    research = await _research_rows(db) if page else []
    items = []
    for o in page:
        summary = o.summary()
        photo = svc.best_photo(
            i for r in svc.research_for(o, research) for i in (r.images or [])
        )
        summary["photo_url"] = photo["image_url"] if photo else None
        items.append(OfficerSummary(**summary))
    return OfficerListOut(items=items, total=len(found), page=pg.page, page_size=pg.page_size)


@router.get("/{officer_id}", response_model=OfficerProfile, summary="One officer's profile")
async def get_officer(
    officer_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Identity, bio, current posting, career timeline, stats, related officers,
    and what the Officer Research Agent found (press, photos, Wikipedia).

    ``officer_id`` is the ``id`` from the directory (or ``officer_id`` on a
    transfer record or feed record). A bare name such as ``Anita Sharma`` also
    works; when several officers share it, the best match is returned and the
    rest are listed under ``alternates``. Admins also see hidden images.
    """
    officer, alternates, officers = await _find(db, officer_id)
    payload = svc.profile(officer, officers, alternates)
    view = svc.research_view(
        svc.research_for(officer, await _research_rows(db)),
        include_hidden=user.role.value == "admin",
    )
    payload["research"] = view
    payload["photo_url"] = view["photo"]["image_url"] if view and view["photo"] else None
    return payload


@router.post("/{officer_id}/research", response_model=OfficerResearchOut,
             summary="Queue this officer for the Officer Research Agent")
async def queue_research(
    officer_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Put the officer at the front of the research queue.

    The agent runs inside the crawl (the scheduled cycle or "Crawl now"), not
    in this request, so the answer comes back with ``status: queued``.
    """
    officer, _alt, _all = await _find(db, officer_id)
    row = (await db.execute(
        select(OfficerResearch).where(OfficerResearch.officer_key == officer.key)
    )).scalars().first()
    if row is None:
        row = OfficerResearch(officer_key=officer.key, name_key=officer.key.partition("|")[0],
                              state=officer.state, officer_name=officer.name, attempts=0,
                              press=[], images=[])
        db.add(row)
    row.officer_id = officer.id
    row.status = "queued"
    row.requested_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return svc.research_view([row], include_hidden=True)


@router.patch("/{officer_id}/images", response_model=OfficerResearchOut,
              summary="Hide or restore a photo on this officer's profile")
async def set_image_visibility(
    officer_id: str,
    body: ImageVisibility,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Hide a wrong or unsuitable photo (or restore it). Stays hidden when the
    agent researches the officer again."""
    officer, _alt, _all = await _find(db, officer_id)
    rows = svc.research_for(officer, await _research_rows(db))
    changed = False
    for row in rows:
        images = [dict(i) for i in (row.images or [])]
        for img in images:
            if img["image_url"] == body.image_url:
                img["hidden"] = body.hidden
                changed = True
        row.images = images  # reassign so SQLAlchemy sees the JSONB change
    if not changed:
        raise HTTPException(404, "Image not found on this officer's profile")
    await db.commit()
    return svc.research_view(rows, include_hidden=True)
