"""Tests for source-trust weighting used in confidence scoring."""
from __future__ import annotations

from app.agents.sources import source_weight


def test_government_sources_score_highest():
    # PIB / gov.in are government-grade -> ~1.0, well above an unknown blog.
    pib = source_weight("PIB", "https://pib.gov.in/PressReleasePage.aspx")
    govin = source_weight("State GAD", "https://up.gov.in/orders/1147.pdf")
    unknown = source_weight("Some Blog", "https://randomblog.example/post")
    assert pib > unknown
    assert govin > unknown
    assert pib >= 0.95
    assert govin >= 0.95


def test_unknown_source_gets_default_0_6():
    assert source_weight("Random Site", "https://unknown.example/x") == 0.6
    assert source_weight(None, None) == 0.6


def test_wire_above_unknown_below_government():
    ani = source_weight("ANI", "https://aninews.in/story")
    pib = source_weight("PIB", "https://pib.gov.in/x")
    unknown = source_weight("blog", "https://nowhere.example")
    assert unknown < ani < pib


def test_match_can_come_from_url_or_name():
    # The matcher searches both the source name and the URL.
    by_url = source_weight("Unknown", "https://www.thehindu.com/news/national/x")
    by_name = source_weight("timesofindia", None)
    assert by_url > 0.6
    assert by_name > 0.6
