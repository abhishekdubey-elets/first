"""The discovery cycle runs one-at-a-time and reports its state."""
from __future__ import annotations

import threading

from app.workers import tasks


def test_only_one_cycle_runs_at_a_time(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_cycle(trigger):
        started.set()
        release.wait(timeout=5)
        return {"ok": True, "trigger": trigger}

    monkeypatch.setattr(tasks, "_run_cycle_locked", slow_cycle)

    results = {}
    t = threading.Thread(target=lambda: results.update(first=tasks.run_discovery_cycle("a")))
    t.start()
    assert started.wait(timeout=5)
    assert tasks.cycle_status()["running"] is True
    assert tasks.cycle_status()["trigger"] == "a"

    second = tasks.run_discovery_cycle("b")
    assert second.get("skipped") is True

    release.set()
    t.join(timeout=5)
    assert results["first"] == {"ok": True, "trigger": "a"}
    state = tasks.cycle_status()
    assert state["running"] is False
    assert state["last_result"] == {"ok": True, "trigger": "a"}
    assert state["last_error"] is None


def test_failed_cycle_records_error_and_releases_lock(monkeypatch):
    def failing(trigger):
        raise RuntimeError("db down")

    monkeypatch.setattr(tasks, "_run_cycle_locked", failing)
    try:
        tasks.run_discovery_cycle("x")
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected the error to propagate")
    state = tasks.cycle_status()
    assert state["running"] is False
    assert "db down" in (state["last_error"] or "")
    # Lock released: a new cycle can start.
    monkeypatch.setattr(tasks, "_run_cycle_locked", lambda trigger: {"ok": 1})
    assert tasks.run_discovery_cycle("y") == {"ok": 1}
