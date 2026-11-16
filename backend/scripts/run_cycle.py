"""Run the discovery pipeline once (or until the backlog clears), then exit.

This is the entry point used by the scheduled GitHub Actions workflow. The
pipeline is plain Python over Supabase and the LLM APIs — it does not need the
web server — so a CI runner can host it even though the API itself lives on
serverless Vercel, where a 60-second function cannot run a 25-minute cycle.

    python -m scripts.run_cycle                 # one cycle
    python -m scripts.run_cycle --deadline 3600 # keep going for an hour
    python -m scripts.run_cycle --max-runs 5

Repeating matters after an outage: one cycle only processes the articles that
fit in CYCLE_TIME_BUDGET_SECONDS, so a backlog needs several passes. The loop
stops early once the pipeline reports nothing left to process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.workers.tasks import run_discovery_cycle  # noqa: E402


def check_database_configured() -> str | None:
    """Explain a missing database URL instead of failing deep in the pipeline.

    Unset secrets leave the defaults in place, which point at localhost — on a
    CI runner that surfaces as a bare 'connection refused' several layers down.
    """
    for name in ("DATABASE_URL", "DATABASE_URL_SYNC"):
        url = getattr(settings, name)
        if "localhost" in url or "127.0.0.1" in url:
            return (
                f"{name} still points at localhost, so the repository secret is "
                "not set. Add DATABASE_URL and DATABASE_URL_SYNC (Supabase "
                "Session Pooler, port 5432) under Settings -> Secrets and "
                "variables -> Actions."
            )
    return None


def check_llm_reachable() -> str | None:
    """Spend one tiny completion to prove extraction can actually run.

    An exhausted balance is only visible per-article, deep in the cycle: the
    crawl still "succeeds" while every extraction returns 429 and the feed
    quietly stops growing. Failing here instead makes the run go red on the
    first day rather than the day someone notices the data is stale.
    """
    from app.services import llm

    provider = llm.active_provider()
    if not llm.is_available(provider):
        return f"No API key is configured for LLM_PROVIDER={provider}."
    try:
        llm.complete_text("Reply with OK.", "ping", max_tokens=5, timeout=30)
    except Exception as exc:  # noqa: BLE001 — any failure here stops the cycle
        return (
            f"{provider} ({llm.active_model(provider)}) rejected a test call, so "
            f"every extraction would fail: {str(exc)[:300]}"
        )
    print(
        f"[run_cycle] {provider} ({llm.active_model(provider)}) reachable; "
        f"key fingerprint {_key_fingerprint(provider)}",
        flush=True,
    )
    return None


def _key_fingerprint(provider: str) -> str:
    """First bytes of the key's SHA-256, to tell deployed keys apart in logs.

    A hash, never the key itself: enough to confirm which credential a runner
    picked up without putting the secret anywhere it could be read.
    """
    key = (
        settings.ANTHROPIC_API_KEY if provider == "anthropic" else settings.OPENAI_API_KEY
    ) or ""
    return hashlib.sha256(key.encode()).hexdigest()[:8] if key else "none"


def fail(message: str) -> None:
    """Report why the run stopped, where whoever is looking will see it.

    On GitHub Actions the log needs a signed-in collaborator, so the reason is
    also raised as an error annotation, which shows on the run's summary page.
    """
    print(f"[run_cycle] {message}", file=sys.stderr, flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Crawl stopped::{escaped}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-runs", type=int, default=1,
                    help="Maximum cycles to run (default 1).")
    ap.add_argument("--deadline", type=int, default=0,
                    help="Wall-clock budget in seconds; 0 means no limit.")
    args = ap.parse_args()

    configure_logging()

    for problem in (check_database_configured(), check_llm_reachable()):
        if problem:
            fail(problem)
            return 2

    started = time.monotonic()
    totals = {"articles": 0, "transfers": 0, "new": 0, "failed": 0}
    remaining: int | None = None

    for run in range(1, args.max_runs + 1):
        if args.deadline and time.monotonic() - started >= args.deadline:
            print(f"[run_cycle] deadline reached before run {run}", flush=True)
            break

        print(f"[run_cycle] starting cycle {run}/{args.max_runs}", flush=True)
        result = run_discovery_cycle("github-actions")
        print(f"[run_cycle] cycle {run}: {json.dumps(result, default=str)}", flush=True)

        if result.get("skipped"):
            break
        # The per-article counters live under "processed", not at the top level.
        processed = result.get("processed") or {}
        for key in totals:
            value = processed.get(key)
            if isinstance(value, int):
                totals[key] += value

        remaining = processed.get("remaining")
        if not remaining:
            print("[run_cycle] no articles left to process", flush=True)
            break

    print(f"[run_cycle] done: {json.dumps(totals)} remaining={remaining}", flush=True)

    # Articles that all fail to extract mean a broken pipeline, not a quiet news
    # day: report it so the scheduled run goes red instead of silently green.
    if totals["failed"] and not totals["transfers"]:
        fail(
            f"{totals['failed']} article(s) failed and nothing was extracted — "
            "treating this cycle as failed."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
