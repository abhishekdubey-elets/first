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
import json
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


def main() -> int:
    problem = check_database_configured()
    if problem:
        print(f"[run_cycle] {problem}", file=sys.stderr, flush=True)
        return 2

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-runs", type=int, default=1,
                    help="Maximum cycles to run (default 1).")
    ap.add_argument("--deadline", type=int, default=0,
                    help="Wall-clock budget in seconds; 0 means no limit.")
    args = ap.parse_args()

    configure_logging()
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
        for key in totals:
            value = result.get(key)
            if isinstance(value, int):
                totals[key] += value

        remaining = result.get("remaining")
        if not remaining:
            print("[run_cycle] no articles left to process", flush=True)
            break

    print(f"[run_cycle] done: {json.dumps(totals)} remaining={remaining}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
