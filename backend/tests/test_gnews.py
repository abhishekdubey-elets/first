"""Offline tests for the Google News link resolver."""
from __future__ import annotations

import base64

from app.services import gnews


def _legacy_id(url: str) -> str:
    payload = url.encode()
    raw = b"\x08\x13\x22" + bytes([len(payload)]) + payload + b"\xd2\x01\x00"
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_is_google_news_url():
    assert gnews.is_google_news_url("https://news.google.com/rss/articles/CBMi?oc=5")
    assert not gnews.is_google_news_url("https://www.thehindu.com/news/x")
    assert not gnews.is_google_news_url(None)


def test_legacy_id_decodes_offline():
    url = "https://www.example.com/news/ias-transfer-2026"
    assert gnews.decode_legacy_id(_legacy_id(url)) == url


def test_new_format_id_needs_network():
    # Current ids carry an opaque AU_yqL token instead of the URL.
    assert gnews.decode_legacy_id(_legacy_id("AU_yqLabcdef")) is None
    assert gnews.decode_legacy_id("not base64!!") is None


def test_resolve_uses_cache_and_never_raises(monkeypatch):
    calls = []

    def boom(article_id, timeout):
        calls.append(article_id)
        raise RuntimeError("network down")

    monkeypatch.setattr(gnews, "_resolve_signed", boom)
    gnews._cache.clear()
    url = "https://news.google.com/rss/articles/" + _legacy_id("AU_yqLxyz") + "?oc=5"
    assert gnews.resolve(url) is None
    assert gnews.resolve(url) is None  # cached miss: no second network attempt
    assert len(calls) == 1
    assert gnews.resolve("https://example.com/not-google") is None


def test_rate_limit_backoff_skips_network(monkeypatch):
    calls = []

    class _Page:
        status_code = 429
        url = "https://www.google.com/sorry/index?continue=x"
        text = ""

    class _Client:
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get(self, url):
            calls.append(url)
            return _Page()

    monkeypatch.setattr(gnews.httpx, "Client", _Client)
    gnews._cache.clear()
    gnews._backoff_until = 0.0
    a = "https://news.google.com/rss/articles/" + _legacy_id("AU_yqLone") + "?oc=5"
    b = "https://news.google.com/rss/articles/" + _legacy_id("AU_yqLtwo") + "?oc=5"
    assert gnews.resolve(a) is None
    assert gnews.is_rate_limited()
    assert gnews.resolve(b) is None  # skipped without a request
    assert len(calls) == 1
    gnews._backoff_until = 0.0
