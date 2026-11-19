#!/usr/bin/env python3
"""Recalculate projects_stats for ongoing projects, then copy every project's
totals into projects_stats_history.

Run nightly by scripts/run_nightly_reports.sh. Safe to re-run the same day
(the day's copy is overwritten). Needs db/projects_stats_history.sql.

    --copy-only   skip the recalculation and only copy projects_stats as it is

Exit code 1 when the copy failed or any project could not be recalculated
(those projects are still copied, with their previous totals).
"""

from __future__ import annotations

import argparse
import sys

import settings  # noqa: F401  (database settings for osprey.db)
from logger import logger
from osprey.services import stats_history


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--copy-only', action='store_true',
                        help='do not recalculate projects_stats first')
    args = parser.parse_args(argv)

    failed = []
    if not args.copy_only:
        done, failed = stats_history.refresh_project_stats()
        print(f"recalculated projects_stats for {done} ongoing project(s)")
        if failed:
            print("WARNING: could not recalculate project(s) {}; see the app log".format(
                ', '.join(str(pid) for pid in failed)), file=sys.stderr)

    try:
        count = stats_history.snapshot()
    except Exception:  # boundary: cron entry point; log and report failure through the exit code
        logger.exception("projects_stats_history snapshot failed")
        print("snapshot failed; see the app log", file=sys.stderr)
        return 1
    print(f"copied totals of {count} project(s) into projects_stats_history")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
