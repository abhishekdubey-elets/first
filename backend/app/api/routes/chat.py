"""RAG assistant endpoint — natural-language Q&A over the transfer records."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import IasTransfer
from app.services import rag

router = APIRouter(prefix="/chat", tags=["chat"])

_FIELDS = (
    "id", "officer_name", "ias_batch", "cadre", "state", "previous_district",
    "previous_posting", "new_district", "new_posting", "transfer_date",
    "notification_number", "source_name", "source_url", "updated_at",
)


class ChatRequest(BaseModel):
    question: str


@router.post("/ask")
async def ask(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_user),
):
    question = (payload.question or "").strip()
    if not question:
        return {"answer": "Ask me something about the IAS transfers, e.g. "
                          "“Who is the new Patna DM?”", "sources": []}

    rows = (await db.execute(
        select(IasTransfer).order_by(IasTransfer.created_at.desc())
    )).scalars().all()
    records = []
    for r in rows:
        d = {f: getattr(r, f, None) for f in _FIELDS}
        d["status"] = r.status.value if r.status else None
        records.append(d)

    # Embedding + LLM calls are blocking — run off the event loop.
    return await asyncio.to_thread(rag.answer, question, records)
