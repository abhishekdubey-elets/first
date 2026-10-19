"""Response models for the public JSON feed.

These exist so the OpenAPI document actually describes a record — every field,
its type, and a worked example — instead of an empty schema. Declaring them as
``response_model`` also pins the key order and guarantees the twelve CXO
Movement Tracker keys come first, which is the contract the Elets portal reads.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_EXAMPLE_RECORD = {
    "date": "2026-09-02",
    "person": "Rajeev Singh Thakur",
    "movement": "Appointment",
    "role": "Chief Secretary, Manipur",
    "role_group": "Chief Secretary",
    "company": "Government of Manipur",
    "moved_from": "",
    "moved_from_source": "",
    "sector": "Government",
    "region": "India",
    "headline": "IAS Rajeev Singh Thakur Appointed Manipur Chief Secretary",
    "source_count": 2,
    "id": 2,
    "state": "Manipur",
    "cadre": "Manipur",
    "batch": "1994",
    "district": "Imphal",
    "moved_from_district": "",
    "order_number": "",
    "order_link": "",
    "source": "APAC Media",
    "status": "exported",
    "updated": "2026-09-02T09:44:21+00:00",
}


class FeedRecord(BaseModel):
    """One officer movement, in the CXO Movement Tracker record shape."""

    model_config = ConfigDict(json_schema_extra={"example": _EXAMPLE_RECORD})

    # --- the twelve CXO Movement Tracker keys, in order ---------------------
    date: str = Field(description="Calendar date of the movement, YYYY-MM-DD.")
    person: str = Field(description="Officer name.")
    movement: str = Field(description=(
        "Transfer, Appointment, Promotion, Retirement, Resignation or "
        "Re-appointment. 'Transfer' extends the tracker's vocabulary."
    ))
    role: str = Field(description="Post the officer moves into.")
    role_group: str = Field(description=(
        "Chief Secretary, District Magistrate / Collector, Secretary, "
        "Commissioner, Sub-Divisional Magistrate, Managing Director / CEO, "
        "Director, Chairman or Other."
    ))
    company: str = Field(description="Employing government, e.g. 'Government of Bihar'.")
    moved_from: str = Field(description="Previous district or posting; empty when unknown.")
    moved_from_source: str = Field(description="'article' when a previous posting is known, else empty.")
    sector: str = Field(description="Always 'Government'.")
    region: str = Field(description="Always 'India'.")
    headline: str = Field(description=(
        "Source article headline. A reshuffle article covering several officers "
        "gives the same headline to each of its records."
    ))
    source_count: int = Field(description="How many articles reported this movement.", ge=1)

    # --- IAS-specific extras; a CXO-shaped consumer ignores these -----------
    id: int = Field(description="Stable record id.")
    state: str = Field(description="Indian state or union territory.")
    cadre: str = Field(description="IAS state cadre.")
    batch: str = Field(description="IAS batch year, as written in the article.")
    district: str = Field(description="Destination district.")
    moved_from_district: str = Field(description="Origin district.")
    order_number: str = Field(description="Government order number.")
    order_link: str = Field(description="Link to the government order, when published.")
    source: str = Field(description="Publisher name. The article URL is deliberately not published.")
    status: str = Field(description="pending, verified, conflicted, exported or export_failed.")
    updated: str = Field(description="When this record last changed, ISO-8601 UTC.")


class FeedResponse(BaseModel):
    """Envelope returned by ``/ias.json`` and ``/ias_latest.json``."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "api_version": "1",
        "source": "IAS Transfer Intelligence",
        "sector": "Government",
        "updated": "2026-09-03T07:05:48+00:00",
        "count": 1,
        "records": [_EXAMPLE_RECORD],
    }})

    api_version: str = Field(description="Feed format version. '1' matches the CXO tracker.")
    source: str = Field(description="Name of the publishing system.")
    sector: str = Field(description="Always 'Government' for this feed.")
    updated: str = Field(description="When the pipeline last completed a crawl.")
    count: int = Field(description="Number of records in this response.")
    records: list[FeedRecord]


class FeedCounts(BaseModel):
    ias: int = Field(description="Total transfer records available.")
    ias_latest: int = Field(description="Records returned by ias_latest.json.")
    articles: int = Field(description="News articles currently retained.")


class FeedIndexResponse(BaseModel):
    """Manifest returned by ``/index.json``."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "api_version": "1",
        "source": "IAS Transfer Intelligence",
        "updated": "2026-09-03T07:05:48+00:00",
        "counts": {"ias": 412, "ias_latest": 50, "articles": 238},
        "refresh_interval_seconds": 86400,
        "endpoints": ["ias.json", "ias_latest.json", "index.json"],
    }})

    api_version: str
    source: str
    updated: str
    counts: FeedCounts
    refresh_interval_seconds: int = Field(description="How often the crawl runs.")
    endpoints: list[str]
