#!/usr/bin/env python3
"""Count files_exif rows per project into exif_counts (nightly).

files_exif holds one row per EXIF tag per file, so counting it is a full
index scan; this runs out-of-band (scripts/run_nightly_reports.sh) and the
/sysadmin/schema/ page only reads the small exif_counts table.

Usage (from the web_app root, with settings.py available):
    PYTHONPATH=. python scripts/count_exif.py

Requires db/exif_counts.sql. Exit code 0 on success, 1 on failure.
"""

from __future__ import annotations

import time

import settings
from logger import logger
from osprey.db import executemany, run_query

# Per-file aggregation first: it walks the files_exif.file_id index once,
# then joins only one row per file to files/folders instead of one per tag.
COUNT_BY_PROJECT = """
    SELECT COALESCE(fo.project_id, 0) AS project_id,
           SUM(e.n) AS exif_rows,
           COUNT(*) AS files_with_exif
    FROM (SELECT file_id, COUNT(*) AS n
          FROM files_exif WHERE file_id IS NOT NULL
          GROUP BY file_id) e
    LEFT JOIN files f ON f.file_id = e.file_id
    LEFT JOIN folders fo ON fo.folder_id = f.folder_id
    GROUP BY COALESCE(fo.project_id, 0)
"""

# Legacy rows written by file_uid (transcription files) have no file_id.
COUNT_UNLINKED = "SELECT COUNT(*) AS n FROM files_exif WHERE file_id IS NULL"

UPSERT = (
    "INSERT INTO exif_counts (project_id, exif_rows, files_with_exif, computed_at, duration_ms) "
    "VALUES (%s, %s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE exif_rows = VALUES(exif_rows), "
    "  files_with_exif = VALUES(files_with_exif), computed_at = VALUES(computed_at), "
    "  duration_ms = VALUES(duration_ms)"
)


def count_exif() -> int:
    run_at = run_query("SELECT NOW() AS now", log_vals=False)[0]['now']
    start = time.monotonic()
    counts = {int(r['project_id']): [int(r['exif_rows']), int(r['files_with_exif'])]
              for r in run_query(COUNT_BY_PROJECT, log_vals=False)}
    unlinked = int(run_query(COUNT_UNLINKED, log_vals=False)[0]['n'])
    if unlinked:
        counts.setdefault(0, [0, 0])[0] += unlinked
    duration_ms = int((time.monotonic() - start) * 1000)

    rows = [(pid, n_rows, n_files, run_at, duration_ms) for pid, (n_rows, n_files) in counts.items()]
    if rows:
        executemany(UPSERT, rows)
    # Projects that no longer have EXIF rows (or were deleted) keep an older
    # computed_at; drop them so the table matches this run. Readers may see
    # the new rows before this delete lands, which only shows extra stale rows.
    run_query("DELETE FROM exif_counts WHERE computed_at < %(run_at)s",
              {'run_at': run_at}, return_val=False, log_vals=False)
    logger.info("count_exif: {} project rows in {} ms".format(len(rows), duration_ms))
    return len(rows)


def main() -> int:
    _ = settings.host
    try:
        count_exif()
    except Exception:
        logger.exception("count_exif: failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
