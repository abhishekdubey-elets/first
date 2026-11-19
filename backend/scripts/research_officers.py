"""Run the Officer Research Agent by hand.

    python -m scripts.research_officers                       # one batch, as the cycle does
    python -m scripts.research_officers --limit 50            # a bigger batch
    python -m scripts.research_officers --officer "Anita Sharma"   # one officer, now

``--officer`` takes a profile id (anita-sharma--uttar-pradesh) or a name, and
runs even when ENABLE_OFFICER_RESEARCH is off.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging  # noqa: E402
from app.workers.tasks import research_officers  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="officers in this batch")
    parser.add_argument("--officer", default=None, help="profile id or name to research now")
    args = parser.parse_args()
    configure_logging()
    print(json.dumps(research_officers(limit=args.limit, officer_ref=args.officer), indent=2))


if __name__ == "__main__":
    main()
