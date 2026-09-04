"""The public feed must keep the CXO Movement Tracker record contract."""
from __future__ import annotations

from datetime import datetime, timezone

from app.api.routes import feed
from app.api.routes.feed import (
    CXO_KEYS, company_of, movement_of, parse_loose_date, record_date,
    role_group_of, role_of, to_record,
)


class _T:
    """Stand-in for an IasTransfer row."""

    def __init__(self, **kw):
        defaults = dict(
            id=1, officer_name="Anita Sharma", ias_batch="2009", cadre="Uttar Pradesh",
            state="Uttar Pradesh", current_designation=None,
            previous_district=None, previous_posting=None,
            new_district=None, new_posting=None,
            transfer_date=None, effective_date=None, reason=None,
            notification_number=None, gov_order_link=None,
            source_name="The Hindu", source_url="https://example.com/a",
            source_headline=None, corroborating_sources=[], status="verified",
            created_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            _news_date=None,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)

    @property
    def news_date(self):
        return self._news_date


def test_record_keeps_the_twelve_cxo_keys_first_and_in_order():
    rec = to_record(_T())
    assert tuple(list(rec)[: len(CXO_KEYS)]) == CXO_KEYS


def test_extras_come_after_and_never_shadow_a_cxo_key():
    rec = to_record(_T())
    extras = list(rec)[len(CXO_KEYS):]
    assert extras, "IAS-specific extras should be present"
    assert not set(extras) & set(CXO_KEYS)


def test_constant_columns_match_the_feed_identity():
    rec = to_record(_T())
    assert rec["sector"] == "Government"
    assert rec["region"] == "India"
    assert rec["source_count"] == 1                      # never zero
    assert to_record(_T(corroborating_sources=["a", "b", "c"]))["source_count"] == 3


def test_loose_dates_reject_missing_components():
    assert parse_loose_date("2026-08-15").date().isoformat() == "2026-08-15"
    assert parse_loose_date("15 August 2026").date().isoformat() == "2026-08-15"
    assert parse_loose_date("15/08/2026").date().isoformat() == "2026-08-15"
    # No day, no month, or no date at all: rejected rather than guessed.
    assert parse_loose_date("August 2026") is None
    assert parse_loose_date("2026") is None
    assert parse_loose_date("with immediate effect") is None
    assert parse_loose_date("Monday") is None
    assert parse_loose_date(None) is None
    assert parse_loose_date("") is None


def test_date_falls_back_through_transfer_then_news_then_created():
    assert record_date(_T(transfer_date="2026-08-15")) == "2026-08-15"
    assert record_date(_T(transfer_date="with immediate effect",
                          effective_date="01 Sep 2026")) == "2026-09-01"
    assert record_date(_T(transfer_date="TBA",
                          _news_date=datetime(2026, 8, 20, tzinfo=timezone.utc))) == "2026-08-20"
    assert record_date(_T()) == "2026-09-01"             # created_at


def test_far_off_transfer_dates_fall_back_to_the_news_date():
    news = datetime(2026, 9, 1, tzinfo=timezone.utc)
    # An old order date quoted in the article must not backdate the record...
    assert record_date(_T(transfer_date="26 May 2026", _news_date=news)) == "2026-09-01"
    # ...but a date a couple of weeks either side is trusted.
    assert record_date(_T(transfer_date="20 Aug 2026", _news_date=news)) == "2026-08-20"
    assert record_date(_T(transfer_date="15 Sep 2026", _news_date=news)) == "2026-09-15"


def test_feed_normalises_batch_and_district_on_output():
    rec = to_record(_T(ias_batch="2023 बैच", new_district="Imphal, Manipur"))
    assert rec["batch"] == "2023"
    assert rec["district"] == "Imphal"


def test_movement_reads_the_event_not_just_the_posting():
    assert movement_of(_T(new_posting="DM Lucknow", previous_district="Varanasi")) == "Transfer"
    assert movement_of(_T(new_posting="DM Lucknow")) == "Appointment"
    assert movement_of(_T(reason="Superannuation on 31 August")) == "Retirement"
    assert movement_of(_T(source_headline="Chief Secretary steps down")) == "Resignation"
    assert movement_of(_T(reason="Promoted to Principal Secretary")) == "Promotion"
    assert movement_of(_T(reason="Extension of tenure by one year")) == "Re-appointment"


def test_role_group_disambiguates_similar_titles():
    assert role_group_of("Chief Secretary, Manipur") == "Chief Secretary"
    assert role_group_of("Principal Secretary, Home") == "Secretary"
    assert role_group_of("District Magistrate, Lucknow") == "District Magistrate / Collector"
    assert role_group_of("Deputy Commissioner, Kangra") == "District Magistrate / Collector"
    assert role_group_of("Divisional Commissioner, Meerut") == "Commissioner"
    assert role_group_of("Municipal Commissioner") == "Commissioner"
    assert role_group_of("Managing Director, State Power Corp") == "Managing Director / CEO"
    assert role_group_of("Chief Electoral Officer") == "Other"


def test_role_falls_back_to_the_destination_district():
    assert role_of(_T(new_posting="DM Lucknow")) == "DM Lucknow"
    assert role_of(_T(current_designation="Joint Secretary")) == "Joint Secretary"
    assert role_of(_T(new_district="Patna")) == "Collector, Patna"
    assert role_of(_T()) == "IAS Officer"


def test_company_is_the_government_not_a_firm():
    assert company_of(_T(state="Bihar")) == "Government of Bihar"
    assert company_of(_T(state="AGMUT")) == "AGMUT Cadre"
    assert company_of(_T(state=None, cadre="Kerala")) == "Kerala Cadre"
    assert company_of(_T(state=None, cadre=None)) == "Government of India"


def test_headline_survives_the_article_purge():
    kept = to_record(_T(source_headline="12 IAS officers transferred in Bihar"))
    assert kept["headline"] == "12 IAS officers transferred in Bihar"

    # Article aged out of the news feed: a plain sentence is synthesised.
    orphan = to_record(_T(new_posting="DM Lucknow", new_district="Lucknow",
                          previous_district="Varanasi"))
    assert orphan["headline"] == "Anita Sharma transferred as DM Lucknow"
    assert "None" not in orphan["headline"]


def test_no_record_value_is_null_where_the_tracker_uses_a_string():
    rec = to_record(_T())
    for key in CXO_KEYS:
        if key == "source_count":
            assert isinstance(rec[key], int)
        else:
            assert isinstance(rec[key], str), f"{key} should be a string, got {rec[key]!r}"


def test_feed_can_be_disabled_and_token_protected(monkeypatch):
    import asyncio

    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(feed.settings, "PUBLIC_FEED_ENABLED", True)
    monkeypatch.setattr(feed.settings, "FEED_TOKEN", "")
    asyncio.run(feed.feed_access(None, None))                   # open by default

    monkeypatch.setattr(feed.settings, "FEED_TOKEN", "s3cret")
    asyncio.run(feed.feed_access("s3cret", None))               # query param
    asyncio.run(feed.feed_access(None, "s3cret"))               # header
    with pytest.raises(HTTPException) as e:
        asyncio.run(feed.feed_access("wrong", None))
    assert e.value.status_code == 401

    monkeypatch.setattr(feed.settings, "PUBLIC_FEED_ENABLED", False)
    with pytest.raises(HTTPException) as e:
        asyncio.run(feed.feed_access("s3cret", None))
    assert e.value.status_code == 404


def test_role_group_handles_hindi_titles():
    assert role_group_of("उपखंड अधिकारी (एसडीएम)") == "Sub-Divisional Magistrate"
    assert role_group_of("एसडीएम (न्यायिक), उरई") == "Sub-Divisional Magistrate"
    assert role_group_of("मुख्य सचिव") == "Chief Secretary"
    assert role_group_of("प्रमुख सचिव, गृह") == "Secretary"
    assert role_group_of("जिलाधिकारी, लखनऊ") == "District Magistrate / Collector"
    assert role_group_of("आयुक्त") == "Commissioner"
    assert role_group_of("निदेशक") == "Director"


def test_response_model_declares_every_record_key_in_order():
    """The OpenAPI schema and the runtime record must agree, key for key."""
    from app.schemas.feed import FeedRecord

    rec = to_record(_T())
    assert list(FeedRecord.model_fields) == list(rec), (
        "FeedRecord and to_record() have drifted apart"
    )
    assert tuple(FeedRecord.model_fields)[: len(CXO_KEYS)] == CXO_KEYS


def test_every_record_field_is_documented():
    from app.schemas.feed import FeedRecord

    undocumented = [n for n, f in FeedRecord.model_fields.items() if not f.description]
    assert not undocumented, f"missing descriptions: {undocumented}"
