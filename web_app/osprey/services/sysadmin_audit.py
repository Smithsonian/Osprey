"""Read-only queries for the sysadmin Audit page (audit_log + ospreyaudit.log).

The table is written by osprey/audit.py (see db/audit_log.sql). Listing is
newest first with keyset paging on audit_id ("before"), so every page is an
index range scan whatever the table size. The details of one event come
from the matching line in ospreyaudit.log (or its rotated copies).
"""

import datetime
import glob
import gzip
import json
import os

from logger import audit_logger
from osprey import db
from osprey.services.sysadmin_data import existing_tables

PAGE_SIZE = 100
# Rotated log files scanned for one event's detail line, newest first.
MAX_LOG_FILES = 30

ENTITIES = ('project', 'folder', 'file')
ACTIONS = ('insert', 'update', 'delete')

_COLUMNS = (
    "audit_id, event_at, actor_type, actor, source, action, entity, event, transcription, "
    "project_id, folder_ref, file_ref, project_alias, folder_name, file_name, note, request_id"
)


def _int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def _text(value, limit=100):
    value = (value or '').strip()
    return value[:limit] or None


def parse_filters(args):
    """Clean filter values from a request's query string (unknown values dropped)."""
    entity = args.get('entity')
    action = args.get('action')
    return {
        'project_id': _int(args.get('project_id')),
        'entity': entity if entity in ENTITIES else None,
        'action': action if action in ACTIONS else None,
        'actor': _text(args.get('actor')),
        'folder_ref': _text(args.get('folder_ref'), 36),
        'file_ref': _text(args.get('file_ref'), 36),
        'request_id': _text(args.get('request_id'), 32),
        'q': _text(args.get('q')),
        'since': _date(args.get('since')),
        'until': _date(args.get('until')),
        'before': _int(args.get('before')),
    }


def _where(filters):
    clauses, params = [], {}
    for column in ('project_id', 'entity', 'action', 'actor', 'folder_ref', 'file_ref', 'request_id'):
        if filters.get(column) is not None:
            clauses.append("{0} = %({0})s".format(column))
            params[column] = filters[column]
    if filters.get('q'):
        clauses.append("(folder_name LIKE %(q)s OR file_name LIKE %(q)s "
                       " OR event LIKE %(q)s OR note LIKE %(q)s)")
        escaped = filters['q'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        params['q'] = '%' + escaped + '%'
    if filters.get('since'):
        clauses.append("event_at >= %(since)s")
        params['since'] = filters['since']
    if filters.get('until'):
        clauses.append("event_at < %(until)s")
        params['until'] = filters['until'] + datetime.timedelta(days=1)
    if filters.get('before'):
        clauses.append("audit_id < %(before)s")
        params['before'] = filters['before']
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def events(filters):
    """One page of audit rows matching ``filters`` (see parse_filters)."""
    if not existing_tables(['audit_log']):
        return {'table_present': False}
    where, params = _where(filters)
    params['limit'] = PAGE_SIZE + 1
    rows = db.run_query(
        "SELECT " + _COLUMNS + " FROM audit_log" + where + " ORDER BY audit_id DESC LIMIT %(limit)s",
        params,
    )
    more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    return {
        'table_present': True,
        'rows': rows,
        'next_before': rows[-1]['audit_id'] if more and rows else None,
        'page_size': PAGE_SIZE,
    }


def filter_options():
    """Projects and actors that appear in the audit log, for the dropdowns."""
    if not existing_tables(['audit_log']):
        return {'projects': [], 'actors': []}
    # GROUP BY on the leading column of an index: a loose index scan.
    projects = db.run_query(
        "SELECT a.project_id, p.project_alias, p.project_title "
        "FROM (SELECT project_id FROM audit_log WHERE project_id IS NOT NULL GROUP BY project_id) a "
        "LEFT JOIN projects p ON p.project_id = a.project_id "
        "ORDER BY p.project_alias, a.project_id"
    )
    actors = db.run_query(
        "SELECT actor, MAX(actor_type) AS actor_type FROM audit_log GROUP BY actor ORDER BY actor"
    )
    return {'projects': projects, 'actors': actors}


def event(audit_id):
    """One audit row, or None."""
    if not existing_tables(['audit_log']):
        return None
    rows = db.run_query("SELECT " + _COLUMNS + " FROM audit_log WHERE audit_id = %(audit_id)s",
                        {'audit_id': audit_id})
    return rows[0] if rows else None


def _log_files():
    """ospreyaudit.log and its rotated copies, newest first."""
    base = next((h.baseFilename for h in audit_logger.handlers if hasattr(h, 'baseFilename')), None)
    if base is None:
        return []
    paths = [p for p in glob.glob(base + '*') if os.path.isfile(p)]
    paths.sort(key=os.path.getmtime, reverse=True)
    return paths[:MAX_LOG_FILES]


def _open(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'r', encoding='utf-8', errors='replace')


def log_details(audit_id):
    """The ospreyaudit.log line for one event, with its details parsed.

    Returns {'found', 'line', 'file', 'details', 'files_searched'}. ``details``
    is the parsed JSON dict, or None if the line could not be parsed.
    """
    needle = "audit_id={} ".format(audit_id)
    files = _log_files()
    for path in files:
        with _open(path) as handle:
            for line in handle:
                if needle not in line:
                    continue
                line = line.rstrip('\n')
                details = None
                if 'details=' in line:
                    try:
                        details = json.loads(line.split('details=', 1)[1])
                    except ValueError:
                        details = None
                return {'found': True, 'line': line, 'file': os.path.basename(path),
                        'details': details, 'files_searched': len(files)}
    return {'found': False, 'line': None, 'file': None, 'details': None,
            'files_searched': len(files)}
