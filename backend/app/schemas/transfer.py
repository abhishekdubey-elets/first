"""Pydantic schemas for transfers and the LLM extraction contract."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExtractedTransfer(BaseModel):
    """The strict contract the Information Extraction Agent must return.

    Every field is optional; the LLM is instructed to return null rather than
    hallucinate. This is parsed directly from the model's JSON response.
    """

    officer_name: str | None = None
    ias_batch: str | None = None
    cadre: str | None = None
    state: str | None = None
    current_designation: str | None = None
    previous_district: str | None = None
    previous_posting: str | None = None
    new_district: str | None = None
    new_posting: str | None = None
    transfer_date: str | None = None
    effective_date: str | None = None
    reason: str | None = None
    notification_number: str | None = None
    gov_order_link: str | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """Top-level LLM response: zero or more transfers found in one article."""

    is_transfer_news: bool = False
    transfers: list[ExtractedTransfer] = Field(default_factory=list)


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    officer_name: str
    ias_batch: str | None
    cadre: str | None
    state: str | None
    current_designation: str | None
    previous_district: str | None
    previous_posting: str | None
    new_district: str | None
    new_posting: str | None
    transfer_date: str | None
    effective_date: str | None
    reason: str | None
    notification_number: str | None
    gov_order_link: str | None
    source_name: str | None
    source_url: str | None
    confidence_score: float
    corroborating_sources: list | None
    discrepancies: list | None
    status: str
    created_at: datetime
    updated_at: datetime


class TransferListOut(BaseModel):
    items: list[TransferOut]
    total: int
    page: int
    page_size: int
