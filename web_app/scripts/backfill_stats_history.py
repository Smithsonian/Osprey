#!/usr/bin/env python3
"""One-off: give projects_stats_history a starting point for a year it has no earlier copy for.

The homepage's "+N in <year>" needs each project's totals from just before
1 January. History began with the first nightly copy, so for that first
year this script rebuilds them: each project's current projects_stats
totals minus the images and objects its files show since 1 January
(capture date, or registration date when that is unknown). They are stored
as copies dated 31 December of the year before.

Projects with no files in Osprey start at their current totals, so they add
nothing to the year. Run it after scripts/snapshot_project_stats.py, so
projects_stats is current.

    backfill_stats_history.py                 show what would be written (default year: this year)
    backfill_stats_history.py --write         write it, keeping any copy already there for that date
    backfill_stats_history.py --write --replace   also overwrite existing copies for that date
    backfill_stats_history.py --year 2026     another year
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import settings  # noqa: F401  (database settings for osprey.db)
from logger import logger
from osprey.services import stats_history


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--year', type=int, default=date.today().year)
    parser.add_argument('--write', action='store_true', help='write the rows (default: only show them)')
    parser.add_argument('--replace', action='store_true', help='with --write, overwrite existing copies')
    args = parser.parse_args(argv)

    try:
        rows = stats_history.backfill_rows(args.year)
    except Exception:  # boundary: CLI entry point
        logger.exception("backfill_stats_history: could not compute rows")
        print("could not compute the starting totals; see the app log", file=sys.stderr)
        return 1

    print(f"{'project':>8}  {'objects at start':>16}  {'images at start':>15}  "
          f"{'objects ' + str(args.year):>13}  {'images ' + str(args.year):>12}  title")
    for row in rows:
        print(f"{row['project_id']:>8}  {row['objects']:>16,}  {row['images']:>15,}  "
              f"{row['objects_since']:>13,}  {row['images_since']:>12,}  {row['project_title'][:50]}"
              + (f"  [{row['error']}]" if row['error'] else ''))
    print(f"total {args.year} work from files: {sum(r['objects_since'] for r in rows):,} objects, "
          f"{sum(r['images_since'] for r in rows):,} images, over {len(rows)} project(s)")
    errors = [r for r in rows if r['error']]
    if errors:
        print(f"WARNING: {len(errors)} project(s) have an invalid project_object_query "
              "and start at their current totals", file=sys.stderr)

    if not args.write:
        print(f"dry run: nothing written. Add --write to store these as copies dated {args.year - 1}-12-31.")
        return 0
    try:
        written = stats_history.write_backfill(rows, args.year, replace=args.replace)
    except Exception:  # boundary: CLI entry point
        logger.exception("backfill_stats_history: write failed")
        print("write failed; see the app log", file=sys.stderr)
        return 1
    print(f"wrote {written} row(s) dated {args.year - 1}-12-31"
          + ("" if args.replace else " (existing copies for that date kept)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
