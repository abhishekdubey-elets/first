"""Tests for the dedup key used by the Duplicate Detection agent.

``compute_dedup_key`` reads its inputs via ``getattr``, so a lightweight object
with the relevant attributes is sufficient — no DB or ORM needed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agents.dedupe import compute_dedup_key


def _t(**kwargs):
    """A transfer-like object with all dedup-relevant fields defaulted to None."""
    base = {
        "officer_name": None,
        "notification_number": None,
        "new_district": None,
        "new_posting": None,
        "transfer_date": None,
        "effective_date": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_same_officer_same_gov_order_number_same_key():
    a = _t(officer_name="Anil Kumar Sharma", notification_number="UP/APP/2026/1147",
           new_district="Kanpur", transfer_date="2026-06-17")
    # Different destination/date but the SAME gov order number -> gov number wins.
    b = _t(officer_name="Anil Kumar Sharma", notification_number="UP/APP/2026/1147",
           new_district="Lucknow", transfer_date="2026-01-01")
    assert compute_dedup_key(a) == compute_dedup_key(b)


def test_same_officer_same_new_posting_and_date_same_key():
    # No gov order number -> key falls back to officer + destination + date.
    a = _t(officer_name="Priya Menon", new_district="Ernakulam", transfer_date="2026-06-16")
    b = _t(officer_name="Priya Menon", new_district="Ernakulam", transfer_date="2026-06-16")
    assert compute_dedup_key(a) == compute_dedup_key(b)


def test_normalization_ignores_case_and_punctuation():
    a = _t(officer_name="Priya Menon", new_district="Ernakulam", transfer_date="2026-06-16")
    b = _t(officer_name="  priya  menon ", new_district="ERNAKULAM!", transfer_date="2026/06/16")
    assert compute_dedup_key(a) == compute_dedup_key(b)


def test_different_officers_different_keys():
    a = _t(officer_name="Anil Kumar Sharma", notification_number="UP/APP/2026/1147")
    b = _t(officer_name="Rajesh Verma", notification_number="UP/APP/2026/1147")
    assert compute_dedup_key(a) != compute_dedup_key(b)


def test_key_is_short_hex():
    key = compute_dedup_key(_t(officer_name="Anil", notification_number="X1"))
    assert len(key) == 32
    assert all(c in "0123456789abcdef" for c in key)
