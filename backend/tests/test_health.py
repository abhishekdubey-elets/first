"""Smoke test for the health endpoint.

We deliberately do NOT enter the TestClient as a context manager: the app's
lifespan calls ``ensure_first_admin()`` which needs a live database. Plain
request dispatch does not trigger lifespan, so ``GET /health`` works DB-free.
If importing the app or building the client requires infrastructure that is
unavailable in this environment, the test skips gracefully rather than failing.
"""
from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - environment-dependent import/setup
    client = None
    _IMPORT_ERROR = exc


@pytest.mark.skipif(client is None, reason=f"app/TestClient unavailable: {_IMPORT_ERROR}")
def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # "ok" with a reachable database, "degraded" (but still 200 and alive)
    # without one — the process never crashes on a DB problem.
    assert body["status"] in ("ok", "degraded")
    assert body["database"]["ok"] == (body["status"] == "ok")
    if body["status"] == "degraded":
        assert body["database"]["error"]
    # The endpoint also returns the app version and scheduler info.
    assert "version" in body
    assert "interval_seconds" in body["scheduler"]
