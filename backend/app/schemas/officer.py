"""Response models for officer profiles (``/api/v1/officers``).

An officer is not stored as a row: a profile is assembled from the transfer
records the pipeline has collected for that person (see
``app.services.officers``). Dates are ``YYYY-MM-DD`` strings derived the same
way as the public feed's ``date`` field.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OfficerMovement(BaseModel):
    """One step of an officer's career: a single transfer record."""

    transfer_id: int
    date: str = Field(description="Best calendar date for the movement (YYYY-MM-DD)")
    stated_date: str | None = Field(
        None, description="Transfer/effective date exactly as the article wrote it"
    )
    movement: str = Field(description="Transfer | Appointment | Promotion | Retirement | ...")
    role: str
    role_group: str
    from_posting: str | None = None
    from_district: str | None = None
    to_posting: str | None = None
    to_district: str | None = None
    state: str | None = None
    reason: str | None = None
    order_number: str | None = None
    order_link: str | None = None
    headline: str
    source_name: str | None = None
    source_url: str | None = None
    source_count: int = 1
    status: str
    is_current: bool = Field(False, description="Part of the most recent movement")
    tenure_days: int | None = Field(
        None,
        description="Days in this posting until the next movement; for a current "
                    "posting, days so far",
    )


class OfficerSummary(BaseModel):
    """Directory entry: who the officer is and where they are now."""

    id: str = Field(description="URL slug; pass it to GET /officers/{id}")
    name: str
    aliases: list[str] = Field(default_factory=list, description="Other spellings seen")
    batch: str | None = None
    cadre: str | None = None
    state: str | None = None
    bio: str = Field(description="One-paragraph summary built from the tracked records")
    photo_url: str | None = Field(
        None, description="Best photo found by the Officer Research Agent (a link, not a copy)"
    )
    current_role: str
    current_district: str | None = None
    current_state: str | None = None
    movements_count: int
    first_seen: str
    last_movement_date: str
    last_movement: str


class OfficerListOut(BaseModel):
    items: list[OfficerSummary]
    total: int
    page: int
    page_size: int


class OfficerLink(BaseModel):
    """A related officer, with why they are related."""

    id: str
    name: str
    batch: str | None = None
    state: str | None = None
    current_role: str
    relation: str = Field(description="same_order | same_article | batchmate | same_name")


class RoleGroupCount(BaseModel):
    role_group: str
    count: int


class OfficerStats(BaseModel):
    movements: int
    distinct_postings: int
    districts: list[str] = Field(description="Districts posted to or from, oldest first")
    states: list[str]
    role_groups: list[RoleGroupCount]
    first_seen: str
    last_seen: str
    average_tenure_days: int | None = Field(
        None, description="Mean days between consecutive movements (null with fewer than two)"
    )
    sources: int = Field(description="Distinct articles that reported this officer")
    verified_movements: int


class SourceLink(BaseModel):
    name: str
    url: str


class OrderLink(BaseModel):
    number: str | None = None
    url: str | None = None
    date: str


class PressMention(BaseModel):
    url: str
    title: str
    source: str | None = None
    published: str | None = Field(None, description="YYYY-MM-DD")
    snippet: str | None = None
    excerpt: str | None = Field(None, description="Text around the officer's name in the article")
    verdict: str | None = Field(
        None, description="How it was judged to be about this officer: llm | context"
    )


class OfficerImage(BaseModel):
    image_url: str
    page_url: str | None = Field(None, description="Where the image was published")
    caption: str | None = Field(None, description="The caption or alt text that names the officer")
    source: str | None = None
    origin: str = Field(description="wikipedia (confirmed) | press (unverified)")
    hidden: bool = False


class WikipediaEntry(BaseModel):
    title: str
    url: str
    extract: str
    image_url: str | None = None
    image_page: str | None = None


class OfficerResearchOut(BaseModel):
    status: str = Field(description="queued | done | failed")
    requested_at: datetime | None = None
    researched_at: datetime | None = None
    error: str | None = None
    press: list[PressMention] = Field(default_factory=list, description="Newest first")
    images: list[OfficerImage] = Field(default_factory=list)
    photo: OfficerImage | None = None
    wikipedia: WikipediaEntry | None = None


class ImageVisibility(BaseModel):
    image_url: str
    hidden: bool = True


class OfficerProfile(OfficerSummary):
    current: OfficerMovement | None = None
    timeline: list[OfficerMovement] = Field(description="Newest first")
    stats: OfficerStats
    sources: list[SourceLink]
    orders: list[OrderLink]
    co_transferred: list[OfficerLink] = Field(
        default_factory=list,
        description="Officers moved in the same government order or reported in the same article",
    )
    batchmates: list[OfficerLink] = Field(default_factory=list)
    alternates: list[OfficerLink] = Field(
        default_factory=list,
        description="Other officers with a matching name (e.g. same name, another state)",
    )
    identity_notes: list[str] = Field(
        default_factory=list,
        description="Where this officer's records disagree about who they are",
    )
    research: OfficerResearchOut | None = Field(
        None, description="Officer Research Agent results; null until researched or queued"
    )


# --- public portal (no login) ------------------------------------------------
class PublicMovement(BaseModel):
    """One career step as published on the portal: no article link."""

    transfer_id: int = Field(description="Same as the feed record's id")
    date: str = Field(description="YYYY-MM-DD")
    stated_date: str | None = None
    movement: str
    role: str
    role_group: str
    from_posting: str | None = None
    from_district: str | None = None
    to_posting: str | None = None
    to_district: str | None = None
    state: str | None = None
    reason: str | None = None
    order_number: str | None = None
    order_link: str | None = None
    headline: str
    source_name: str | None = Field(None, description="Publisher name")
    source_count: int = 1
    status: str
    is_current: bool = False
    tenure_days: int | None = None


class NewsMention(BaseModel):
    """A press story about the officer, as a headline (no link or excerpt)."""

    title: str
    source: str | None = Field(None, description="Publisher name")
    published: str | None = Field(None, description="YYYY-MM-DD")


class PublicOfficerProfile(OfficerSummary):
    """``GET /api/v1/ias/officers/{officer_id}.json``: an officer page for the portal.

    ``photo_url`` is the Wikipedia photo only; press photos are unverified and
    stay in the dashboard. Wikipedia text and images are freely licensed and
    must be credited with a link to ``wikipedia.url`` / ``wikipedia.image_page``.
    """

    current: PublicMovement | None = None
    timeline: list[PublicMovement] = Field(description="Newest first")
    stats: OfficerStats
    orders: list[OrderLink]
    co_transferred: list[OfficerLink] = Field(default_factory=list)
    batchmates: list[OfficerLink] = Field(default_factory=list)
    alternates: list[OfficerLink] = Field(default_factory=list)
    wikipedia: WikipediaEntry | None = None
    in_the_news: list[NewsMention] = Field(
        default_factory=list, description="Newest first; empty until the officer is researched"
    )
