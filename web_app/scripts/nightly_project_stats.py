#!/usr/bin/env python3
"""Recalculate projects_stats for ongoing projects, then store this year's new images and objects per project.

Run nightly by scripts/run_nightly_reports.sh. Safe to re-run: the year's
counts are overwritten. The counts need db/projects_stats_yearly.sql.

    nightly_project_stats.py                 recalculate, then count the current year
    nightly_project_stats.py --counts-only   only count the year
    nightly_project_stats.py --year 2025     count another year (with --counts-only to skip the recalculation)

Exit code 1 when any project could not be recalculated or counted, or the
counts could not be stored.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import settings  # noqa: F401  (database settings for osprey.db)
from logger import logger
from osprey.services import yearly_stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--counts-only', action='store_true', help='do not recalculate projects_stats first')
    parser.add_argument('--year', type=int, default=date.today().year)
    args = parser.parse_args(argv)

    problems = False
    if not args.counts_only:
        done, failed = yearly_stats.refresh_project_stats()
        print(f"recalculated projects_stats for {done} ongoing project(s)")
        if failed:
            problems = True
            print("WARNING: could not recalculate project(s) {}; see the app log".format(
                ', '.join(str(pid) for pid in failed)), file=sys.stderr)

    try:
        rows = yearly_stats.compute_year_rows(args.year)
        written = yearly_stats.write_year_rows(rows, args.year)
    except Exception:  # boundary: cron entry point; log and report failure through the exit code
        logger.exception("projects_stats_yearly update failed")
        print(f"{args.year} counts failed; see the app log", file=sys.stderr)
        return 1

    print(f"{args.year}: {sum(r['objects'] for r in rows):,} objects and {sum(r['images'] for r in rows):,} images "
          f"registered; stored for {written} project(s)")
    for row in rows:
        if row['error']:
            problems = True
            print(f"WARNING: project {row['project_id']} ({row['project_title'][:50]}): {row['error']}",
                  file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
