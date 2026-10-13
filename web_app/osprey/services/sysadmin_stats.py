"""Nightly per-project statistics for the sysadmin pages (sysadmin_stats table).

Each job runs one SQL query that returns `project_id` plus one column per
stat; every other column becomes a row (stat_id, project_id, value) in
sysadmin_stats. Jobs run through the report queue as built-in reports
(project_id 0, report_id 'stat:<job_id>'), so report_materializations
records their status, duration and errors like any other nightly job, and
the Status page shows failures.

Adding a stat: add a job to STAT_JOBS (or a column to an existing job's
query and its `stats` mapping). No schema change needed.
"""

from __future__ import annotations

from collections import OrderedDict

from osprey.db import executemany, run_query

# report_materializations rows for stat jobs: not tied to a project.
STAT_PROJECT_ID = 0
REPORT_PREFIX = 'stat:'

# project_id 0 in a job's results means "not linked to a project".
STAT_JOBS = OrderedDict([
    ('files_exif', {
        'title': 'files_exif rows by project',
        'note': 'One row per EXIF tag, so each file has many rows. '
                'Not linked = no file_id (older rows keyed by file_uid) or the file/folder is missing.',
        # Per-file aggregation walks the files_exif.file_id index once and
        # joins files/folders once per file, not once per tag. Rows with no
        # file_id are added to project 0 by the second branch.
        'sql': """
            SELECT project_id,
                   SUM(exif_rows) AS files_exif_rows,
                   SUM(files) AS files_exif_files
            FROM (
                SELECT COALESCE(fo.project_id, 0) AS project_id,
                       SUM(e.n) AS exif_rows, COUNT(*) AS files
                FROM (SELECT file_id, COUNT(*) AS n
                      FROM files_exif WHERE file_id IS NOT NULL
                      GROUP BY file_id) e
                LEFT JOIN files f ON f.file_id = e.file_id
                LEFT JOIN folders fo ON fo.folder_id = f.folder_id
                GROUP BY COALESCE(fo.project_id, 0)
                UNION ALL
                SELECT 0, COUNT(*), 0 FROM files_exif WHERE file_id IS NULL
            ) t
            GROUP BY project_id
        """,
        # Column -> label, in display order. The first one sorts the table.
        'stats': OrderedDict([
            ('files_exif_rows', 'EXIF rows'),
            ('files_exif_files', 'Files with EXIF'),
        ]),
    }),
])


def report_id_for(job_id: str) -> str:
    return REPORT_PREFIX + job_id


def job_id_from_report(report_id: str) -> str | None:
    """Job id for a 'stat:<job_id>' report_id, or None if it is not a stat job."""
    if report_id.startswith(REPORT_PREFIX):
        job_id = report_id[len(REPORT_PREFIX):]
        if job_id in STAT_JOBS:
            return job_id
    return None


def run_job(job_id: str) -> int:
    """Compute one job and replace its stats. Returns rows written.

    Called by scripts/materialize_reports.py. Raises on any error so the
    caller records the job as failed.
    """
    job = STAT_JOBS[job_id]
    run_at = run_query("SELECT NOW() AS now", log_vals=False)[0]['now']
    results = run_query(job['sql'], log_vals=False)
    rows = []
    for r in results:
        missing = [s for s in job['stats'] if s not in r]
        if missing:
            raise KeyError("stat job {} query lacks columns {}".format(job_id, missing))
        for stat_id in job['stats']:
            rows.append((stat_id, int(r['project_id']), int(r[stat_id] or 0), run_at))
    if rows:
        executemany(
            "INSERT INTO sysadmin_stats (stat_id, project_id, value, computed_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = VALUES(computed_at)",
            rows,
        )
    # Drop this job's rows that the run did not refresh (project no longer
    # has data or was deleted). Readers may briefly see them before this
    # lands; they are stale counts, never wrong ones for the current run.
    stat_ids = list(job['stats'])
    placeholders = ', '.join('%(s{})s'.format(i) for i in range(len(stat_ids)))
    params = {'s{}'.format(i): s for i, s in enumerate(stat_ids)}
    params['run_at'] = run_at
    run_query(
        "DELETE FROM sysadmin_stats WHERE stat_id IN (" + placeholders + ") "
        "AND computed_at < %(run_at)s",
        params, return_val=False, log_vals=False,
    )
    return len(rows)
