"""Sysadmin-only reports: SQL queries stored in sysadmin_reports.

Unlike data_reports, these never appear on project dashboards. Two modes:

- live (pregenerated = 0): run when a sysadmin opens the report; shown in
  the page (first PREVIEW_ROWS rows) and downloadable as CSV.
- pregenerated (pregenerated = 1): queued in report_materializations as
  project_id 0, report_id 'sysrep:<report_id>', and run by
  scripts/materialize_reports.py (nightly, or when a sysadmin clicks
  Queue). CSV/XLSX files go to ARTIFACT_DIR, which is outside static/ on
  purpose: static/ is served to anyone, these files are sysadmin-only.

Queries are written by hand in the table (see db/sysadmin_reports.sql) and
run as the app's DB user; check_query() rejects anything but a single
read-only SELECT/WITH statement.
"""

from __future__ import annotations

import csv
import os
import re
import tempfile
import time
from io import StringIO

import pandas as pd

import settings
from logger import logger
from osprey.db import run_query
from osprey.services import report_materializations as materializations

MATERIALIZATION_PROJECT_ID = 0
REPORT_PREFIX = 'sysrep:'
PREVIEW_ROWS = 1000
XLSX_MAX_ROWS = 1048575  # Excel sheet limit minus the header row

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Optional setting; relative paths resolve against the app root like cache.py.
_dir = getattr(settings, 'sysadmin_reports_folder', 'sysadmin_reports')
ARTIFACT_DIR = _dir if os.path.isabs(_dir) else os.path.join(_APP_ROOT, _dir)

REPORT_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
# A single statement only; a trailing semicolon is tolerated.
_LEADING = re.compile(r'^\s*(select|with)\b', re.IGNORECASE)
# Write/lock/file/side-effect constructs a read-only report never needs.
# MySQL 8 allows "WITH ... DELETE/UPDATE", so the leading keyword alone is
# not enough.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|call|"
    r"outfile|dumpfile|load_file|sleep|benchmark|get_lock|for\s+update|"
    r"lock\s+in\s+share\s+mode)\b",
    re.IGNORECASE,
)


class ReportError(Exception):
    """A stored report that cannot be run (bad id, unsafe query, missing)."""


def check_query(sql: str) -> str:
    """Return the query without a trailing ';' or raise ReportError."""
    q = (sql or '').strip().rstrip(';').strip()
    if not q:
        raise ReportError("query is empty")
    if ';' in q:
        raise ReportError("query must be a single statement")
    if not _LEADING.match(q):
        raise ReportError("query must start with SELECT or WITH")
    m = _FORBIDDEN.search(q)
    if m:
        raise ReportError("query contains '{}', which is not allowed in a report".format(m.group(0)))
    return q


def materialization_id(report_id: str) -> str:
    return REPORT_PREFIX + report_id


def report_id_from_materialization(mat_report_id: str) -> str | None:
    if mat_report_id.startswith(REPORT_PREFIX):
        return mat_report_id[len(REPORT_PREFIX):]
    return None


def table_exists() -> bool:
    rows = run_query(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sysadmin_reports'",
        log_vals=False,
    )
    return bool(rows)


def get_report(report_id: str) -> dict | None:
    if not REPORT_ID_RE.match(report_id or ''):
        return None
    rows = run_query(
        "SELECT r.report_id, r.project_id, r.title, r.description, r.query, r.pregenerated, "
        "  r.updated_at, p.project_title, p.project_alias "
        "FROM sysadmin_reports r LEFT JOIN projects p ON p.project_id = r.project_id "
        "WHERE r.report_id = %(report_id)s",
        {'report_id': report_id},
    )
    return rows[0] if rows else None


def list_reports() -> list[dict]:
    """Reports grouped by project (None = all projects), with last runs."""
    rows = run_query(
        "SELECT r.report_id, r.project_id, r.title, r.description, r.pregenerated, r.updated_at, "
        "  p.project_title, p.project_alias, "
        "  m.status, m.last_succeeded_at, m.last_failed_at, m.duration_ms, m.row_count, "
        "  m.error_message, m.artifact_path_csv, m.artifact_path_xlsx "
        "FROM sysadmin_reports r "
        "LEFT JOIN projects p ON p.project_id = r.project_id "
        "LEFT JOIN report_materializations m ON m.project_id = %(mat_pid)s "
        "  AND m.report_id = CONCAT(%(prefix)s, r.report_id) "
        "ORDER BY r.project_id IS NOT NULL, p.project_title, r.title",
        {'mat_pid': MATERIALIZATION_PROJECT_ID, 'prefix': REPORT_PREFIX},
    )
    groups = []
    for r in rows:
        key = r['project_id']
        if not groups or groups[-1]['project_id'] != key:
            groups.append({'project_id': key, 'project_title': r['project_title'],
                           'project_alias': r['project_alias'], 'reports': []})
        groups[-1]['reports'].append(r)
    return groups


def run_live(report: dict) -> dict:
    """Run a live report; returns columns, the first PREVIEW_ROWS rows and the total."""
    q = check_query(report['query'])
    start = time.monotonic()
    rows = run_query(q, log_vals=False)
    return {
        'columns': list(rows[0].keys()) if rows else [],
        'rows': rows[:PREVIEW_ROWS],
        'total': len(rows),
        'duration_ms': int((time.monotonic() - start) * 1000),
    }


def live_csv(report: dict) -> str:
    """Full result of a live report as CSV text.

    Built in memory with the normal buffered query: live reports are small by
    definition (large ones should be pregenerated). Streaming with iter_query
    would hold an unbuffered connection open for the whole download, and a
    client that disconnects midway leaves unread rows on it.
    """
    q = check_query(report['query'])
    rows = run_query(q, log_vals=False)
    out = StringIO()
    writer = csv.writer(out, lineterminator='\n')
    if rows:
        writer.writerow(list(rows[0].keys()))
        for row in rows:
            writer.writerow(['' if v is None else v for v in row.values()])
    return out.getvalue()


def queue(report: dict, requested_by: str | None) -> bool:
    mat_id = materialization_id(report['report_id'])
    materializations.ensure_row(MATERIALIZATION_PROJECT_ID, mat_id)
    return materializations.request_refresh(MATERIALIZATION_PROJECT_ID, mat_id, requested_by=requested_by)


def artifact_path(rel_name: str | None) -> str | None:
    """Absolute path of a stored artifact name, only if it stays in ARTIFACT_DIR."""
    if not rel_name:
        return None
    path = os.path.realpath(os.path.join(ARTIFACT_DIR, rel_name))
    if os.path.dirname(path) != os.path.realpath(ARTIFACT_DIR):
        return None
    return path if os.path.isfile(path) else None


def materialize(report_id: str) -> dict:
    """Run a pregenerated report to CSV (+ XLSX when it fits). Called by
    scripts/materialize_reports.py; raises on failure.

    Files are written to a temp name and renamed, so a download never sees a
    half-written file; the previous run's files are removed afterwards.
    """
    report = get_report(report_id)
    if report is None:
        raise ReportError("sysadmin report {} not found".format(report_id))
    q = check_query(report['query'])
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    df = pd.DataFrame(run_query(q, log_vals=False) or [])
    stamp = time.strftime('%Y%m%d_%H%M%S')
    base = '{}_{}'.format(report_id, stamp)

    names = {'csv': base + '.csv'}
    _write_atomic(os.path.join(ARTIFACT_DIR, names['csv']), lambda p: df.to_csv(p, index=False))
    if len(df.index) <= XLSX_MAX_ROWS:
        names['xlsx'] = base + '.xlsx'
        _write_atomic(os.path.join(ARTIFACT_DIR, names['xlsx']), lambda p: df.to_excel(p, index=False))

    keep = set(names.values())
    for fn in os.listdir(ARTIFACT_DIR):
        if fn.startswith(report_id + '_') and fn not in keep and re.match(
                r'^' + re.escape(report_id) + r'_\d{8}_\d{6}\.(csv|xlsx)$', fn):
            try:
                os.remove(os.path.join(ARTIFACT_DIR, fn))
            except OSError:
                # An old file left behind is harmless; the next run retries.
                logger.warning("sysadmin_reports: could not remove old artifact {}".format(fn), exc_info=True)
    return {'row_count': len(df.index), 'csv': names['csv'], 'xlsx': names.get('xlsx')}


def _write_atomic(path: str, write) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=os.path.splitext(path)[1])
    os.close(fd)
    try:
        write(tmp)
        # Owner + group read: the web server must be able to read files the
        # cron user writes, so they need a shared group (see README).
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
