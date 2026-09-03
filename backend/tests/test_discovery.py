"""Tests for the discovery agent's headline filter, date handling and ordering."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agents import discovery
from app.agents.discovery import _parse_date, looks_relevant


def test_google_news_headlines_need_one_signal():
    assert looks_relevant("IAS officer transferred to Lucknow")
    assert looks_relevant("Rajeev Singh Thakur appointed Manipur Chief Secretary")
    assert looks_relevant("आईएएस अधिकारियों का तबादला")
    assert not looks_relevant("")


def test_general_feeds_need_subject_and_movement():
    # A plain "transfer" headline from a national-news RSS feed is not enough.
    assert not looks_relevant("Transfer window: club signs striker", strict=True)
    assert not looks_relevant("Cabinet secretary meets industry leaders", strict=True)
    assert looks_relevant("12 IAS officers transferred in Bihar reshuffle", strict=True)
    assert looks_relevant("New Collector posted in Pune district", strict=True)


def test_noise_is_rejected_even_with_keywords():
    assert not looks_relevant("IPL transfer: officer of the match moves club")
    assert not looks_relevant("7 letters to police, yet no FIR in 'transfer racket' case")
    assert not looks_relevant("Bank transfer scam targets retired officers")


def test_parse_date_is_aware_utc_and_never_far_future():
    now = datetime.now(timezone.utc)
    ok = _parse_date({"published": "Wed, 02 Sep 2026 06:27:26 GMT"})
    assert ok is not None and ok.tzinfo is not None
    assert ok == datetime(2026, 9, 2, 6, 27, 26, tzinfo=timezone.utc)

    naive = _parse_date({"updated": "2026-09-02T10:00:00"})
    assert naive is not None and naive.tzinfo is not None

    future = (now + timedelta(days=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    clamped = _parse_date({"published": future})
    # Clamped to "now + 5 min" as seen inside the call, so compare against a
    # timestamp taken afterwards.
    assert clamped is not None
    assert clamped <= datetime.now(timezone.utc) + timedelta(minutes=5)
    assert clamped < now + timedelta(days=1)

    assert _parse_date({"published": "not a date"}) is None
    assert _parse_date({}) is None


def test_lookback_window_never_below_two_days(monkeypatch):
    monkeypatch.setattr(discovery.settings, "DISCOVERY_LOOKBACK_HOURS", 6)
    assert "when%3A2d" in discovery._google_news_url("IAS transfer", "en")
    monkeypatch.setattr(discovery.settings, "DISCOVERY_LOOKBACK_HOURS", 72)
    assert "when%3A3d" in discovery._google_news_url("IAS transfer", "en")


class _FakeDB:
    """Records inserted Article objects; nothing exists yet."""

    def __init__(self):
        self.added = []

    def execute(self, *_a, **_k):
        class _R:
            def first(self):
                return None
        return _R()

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def begin_nested(self):
        import contextlib
        return contextlib.nullcontext()


def test_persist_inserts_newest_first_and_dedupes(monkeypatch):
    monkeypatch.setattr(discovery.settings, "DISCOVERY_RESOLVE_GOOGLE_LINKS", False)
    db = _FakeDB()
    agent = discovery.DiscoveryAgent(db)
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 9, 1, tzinfo=timezone.utc)
    cands = [
        {"url": "https://a.example/old", "title": "old", "published_at": old},
        {"url": "https://a.example/new", "title": "new", "published_at": new},
        {"url": "https://a.example/new", "title": "dupe", "published_at": new},
        {"url": "", "title": "no url"},
    ]
    inserted, resolved = agent._persist(cands)
    assert inserted == 2 and resolved == 0
    assert [a.title for a in db.added] == ["new", "old"]


def test_duplicate_insert_is_skipped_not_fatal(monkeypatch):
    """A unique-constraint violation on one article must not abort the batch."""
    from sqlalchemy.exc import IntegrityError

    monkeypatch.setattr(discovery.settings, "DISCOVERY_RESOLVE_GOOGLE_LINKS", False)
    db = _FakeDB()
    calls = {"n": 0}

    def flaky_add(obj):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))
        db.added.append(obj)

    db.add = flaky_add
    agent = discovery.DiscoveryAgent(db)
    inserted, _ = agent._persist([
        {"url": "https://a.example/dupe", "title": "dupe"},
        {"url": "https://a.example/fresh", "title": "fresh"},
    ])
    assert inserted == 1
    assert [a.title for a in db.added] == ["fresh"]
