"""Read-only lookups for the sysadmin pages (users, keys, kiosks, reports...).

Everything here is SELECT-only. Column names follow
osprey_database_structure.sql (parent project) and the hand-applied
db/*.sql files. Each page wraps its calls in system_status.section(), so a
missing table or a DB error shows in that block instead of failing the page.
"""

from collections import OrderedDict

import settings
from osprey import db
from osprey.services import sysadmin_stats

# Hand-applied SQL files and what each one creates. mark_pregenerated_reports.sql
# only changes data, so there is nothing to detect for it.
SCHEMA_CHECKS = (
    ('db/report_materializations.sql', 'report_materializations', None),
    ('db/kiosk.sql', 'kiosk', None),
    ('db/preview_type.sql', 'folders', 'preview_type'),
    ('db/preview_type.sql', 'transcription_folders', 'preview_type'),
    ('db/transcription_profile.sql', 'transcription_profile_settings', None),
    ('db/transcription_profile.sql', 'transcription_profile_terms', None),
    ('db/transcription_profile.sql', 'transcription_profile_fill', None),
    ('db/transcription_profile.sql', 'transcription_profile_results', None),
    ('db/sysadmin.sql', 'users', 'sysadmin'),
    ('db/sysadmin_stats.sql', 'sysadmin_stats', None),
    ('db/sysadmin_reports.sql', 'sysadmin_reports', None),
    ('db/project_custom_data.sql', 'project_custom_values', None),
)

# api_keys_usage is indexed on api_key only (no created_at index), so
# scanning it by date would read the whole log. Instead we read the newest
# N rows by primary key, which is cheap at any table size.
API_USAGE_WINDOW = 100000
API_INVALID_SHOWN = 20

# kiosk is indexed on reported_at; bounding by days keeps the scan small.
KIOSK_DAYS = 30


def _mask_key(key):
    """Show only the last 4 characters of an API key."""
    if not key:
        return ''
    return '…' + str(key)[-4:]


def _in_params(prefix, values):
    """Named placeholders for an IN (...) list: ('%(t0)s, %(t1)s', {...})."""
    params = {'{}{}'.format(prefix, i): v for i, v in enumerate(values)}
    placeholders = ', '.join('%({})s'.format(k) for k in params)
    return placeholders, params


def existing_tables(names):
    names = list(names)
    placeholders, params = _in_params('t', names)
    rows = db.run_query(
        "SELECT TABLE_NAME AS name FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (" + placeholders + ")",
        params,
    )
    return {r['name'] for r in rows}


def schema_status():
    tables = existing_tables({t for _, t, _ in SCHEMA_CHECKS})
    col_checks = [(t, c) for _, t, c in SCHEMA_CHECKS if c]
    t_ph, t_params = _in_params('t', [t for t, _ in col_checks])
    c_ph, c_params = _in_params('c', [c for _, c in col_checks])
    rows = db.run_query(
        "SELECT TABLE_NAME AS t, COLUMN_NAME AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (" + t_ph + ") "
        "AND COLUMN_NAME IN (" + c_ph + ")",
        {**t_params, **c_params},
    )
    columns = {(r['t'], r['c']) for r in rows}
    result = []
    for sql_file, table, column in SCHEMA_CHECKS:
        if column:
            applied = (table, column) in columns
            target = '{}.{}'.format(table, column)
        else:
            applied = table in tables
            target = table
        result.append({'file': sql_file, 'target': target, 'applied': applied})
    return result


def table_sizes():
    # TABLE_ROWS is an InnoDB estimate, and MySQL 8 caches these statistics
    # (information_schema_stats_expiry, 24h by default).
    return db.run_query(
        "SELECT TABLE_NAME AS name, TABLE_ROWS AS est_rows, "
        "  DATA_LENGTH AS data_bytes, INDEX_LENGTH AS index_bytes, "
        "  DATA_LENGTH + INDEX_LENGTH AS total_bytes, UPDATE_TIME AS update_time "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
        "ORDER BY total_bytes DESC"
    )


def users():
    # Never select users.pass.
    return db.run_query(
        "SELECT u.user_id, u.username, u.full_name, u.email, u.user_active, "
        "  u.is_admin, u.sysadmin, u.internal, u.updated_at, "
        "  COUNT(qp.project_id) AS project_count "
        "FROM users u LEFT JOIN qc_projects qp ON qp.user_id = u.user_id "
        "GROUP BY u.user_id, u.username, u.full_name, u.email, u.user_active, "
        "  u.is_admin, u.sysadmin, u.internal, u.updated_at "
        "ORDER BY u.user_active DESC, u.username"
    )


def _assignment_rows():
    return db.run_query(
        "SELECT p.project_id, p.project_alias, p.project_title, p.project_status, "
        "  u.user_id, u.username, u.full_name, u.user_active "
        "FROM qc_projects qp "
        "JOIN projects p ON p.project_id = qp.project_id "
        "JOIN users u ON u.user_id = qp.user_id "
        "ORDER BY p.project_title, u.username"
    )


def assignments_by_user():
    """{user_id: [project rows]} for the users page."""
    grouped = {}
    for r in _assignment_rows():
        grouped.setdefault(r['user_id'], []).append(r)
    return grouped


def projects_overview():
    """Every project with its assigned users and projects_settings values."""
    projects = db.run_query(
        "SELECT project_id, project_alias, project_title, project_status, "
        "  project_unit, qc_status "
        "FROM projects ORDER BY project_status = 'Completed', project_title"
    )
    by_id = OrderedDict((p['project_id'], dict(p, users=[], settings={})) for p in projects)
    for r in _assignment_rows():
        if r['project_id'] in by_id:
            by_id[r['project_id']]['users'].append(r)
    for s in db.run_query(
        "SELECT project_id, project_setting, settings_value FROM projects_settings "
        "ORDER BY project_id, project_setting, settings_value"
    ):
        if s['project_id'] in by_id:
            by_id[s['project_id']]['settings'].setdefault(
                s['project_setting'], []).append(s['settings_value'])
    return list(by_id.values())


def transcription_profile_config():
    """Per-project profile settings and terms; None when the tables are absent."""
    present = existing_tables(['transcription_profile_settings', 'transcription_profile_terms'])
    if len(present) < 2:
        return None
    rows = db.run_query(
        "SELECT s.*, p.project_alias FROM transcription_profile_settings s "
        "LEFT JOIN projects p ON p.project_id = s.project_id ORDER BY s.project_id"
    )
    terms = {}
    for t in db.run_query(
        "SELECT project_id, term_type, term FROM transcription_profile_terms "
        "ORDER BY project_id, term_type, term"
    ):
        terms.setdefault(t['project_id'], {}).setdefault(t['term_type'], []).append(t['term'])
    for r in rows:
        r['terms'] = terms.get(r['project_id'], {})
    return rows


def api_keys():
    keys = db.run_query(
        "SELECT table_id, api_key, api_user, uid, is_active, is_admin, usage_rate, "
        "  expires_on, expires_on < NOW() AS expired, updated_at "
        "FROM api_keys ORDER BY is_active DESC, api_user"
    )
    usage = db.run_query(
        "SELECT api_key, MAX(created_at) AS last_used, "
        "  SUM(created_at >= NOW() - INTERVAL 1 DAY) AS calls_24h, "
        "  SUM(valid = 0) AS invalid "
        "FROM (SELECT api_key, created_at, valid FROM api_keys_usage "
        "      ORDER BY tableid DESC LIMIT %(window)s) recent "
        "GROUP BY api_key",
        {'window': API_USAGE_WINDOW},
    )
    usage_by_key = {u['api_key']: u for u in usage}
    known = set()
    for k in keys:
        known.add(k['api_key'])
        u = usage_by_key.get(k['api_key'], {})
        k['last_used'] = u.get('last_used')
        k['calls_24h'] = int(u.get('calls_24h') or 0)
        k['key_masked'] = _mask_key(k.pop('api_key'))
    invalid = db.run_query(
        "SELECT api_key, url, created_at "
        "FROM (SELECT api_key, url, created_at, valid FROM api_keys_usage "
        "      ORDER BY tableid DESC LIMIT %(window)s) recent "
        "WHERE valid = 0 ORDER BY created_at DESC LIMIT %(shown)s",
        {'window': API_USAGE_WINDOW, 'shown': API_INVALID_SHOWN},
    )
    for row in invalid:
        row['known_key'] = row['api_key'] in known
        row['key_masked'] = _mask_key(row.pop('api_key'))
    return {'keys': keys, 'invalid': invalid, 'window': API_USAGE_WINDOW}


def kiosks():
    if not existing_tables(['kiosk']):
        return {'table_present': False, 'configured': list(settings.kiosks)}
    rows = db.run_query(
        "SELECT machine_name, ip, MAX(reported_at) AS last_seen, COUNT(*) AS checkins "
        "FROM kiosk WHERE reported_at >= NOW() - INTERVAL %(days)s DAY "
        "GROUP BY machine_name, ip ORDER BY machine_name, last_seen DESC",
        {'days': KIOSK_DAYS},
    )
    configured = set(settings.kiosks)
    machines = OrderedDict()
    for r in rows:
        m = machines.setdefault(r['machine_name'], {
            'machine_name': r['machine_name'], 'ip': r['ip'], 'last_seen': r['last_seen'],
            'checkins': 0, 'other_ips': []})
        m['checkins'] += r['checkins']
        if r['ip'] != m['ip']:
            m['other_ips'].append(r['ip'])
    for m in machines.values():
        m['configured'] = m['ip'] in configured
    seen_ips = {m['ip'] for m in machines.values()}
    return {
        'table_present': True,
        'days': KIOSK_DAYS,
        'machines': list(machines.values()),
        'configured_not_seen': sorted(configured - seen_ips),
    }


def reports():
    has_mat = bool(existing_tables(['report_materializations']))
    if has_mat:
        query = (
            "SELECT r.report_id, r.project_id, p.project_alias, r.report_title, "
            "  r.pregenerated, r.updated_at, m.status, m.last_succeeded_at, "
            "  m.duration_ms, m.row_count "
            "FROM data_reports r "
            "LEFT JOIN projects p ON p.project_id = r.project_id "
            "LEFT JOIN report_materializations m "
            "  ON m.project_id = r.project_id AND m.report_id = r.report_id "
            "ORDER BY p.project_alias, r.report_title"
        )
    else:
        query = (
            "SELECT r.report_id, r.project_id, p.project_alias, r.report_title, "
            "  r.pregenerated, r.updated_at "
            "FROM data_reports r LEFT JOIN projects p ON p.project_id = r.project_id "
            "ORDER BY p.project_alias, r.report_title"
        )
    return {'materializations': has_mat, 'rows': db.run_query(query)}



def stats():
    """Nightly per-project stats (sysadmin_stats), grouped by job, with each
    job's last run from report_materializations.

    Never runs the stat queries themselves: they scan very large tables and
    run nightly through the report queue (see sysadmin_stats.py).
    """
    present = existing_tables(['sysadmin_stats', 'report_materializations'])
    if 'sysadmin_stats' not in present:
        return {'table_present': False}
    rows = db.run_query(
        "SELECT s.stat_id, s.project_id, s.value, s.computed_at, "
        "  p.project_alias, p.project_title, p.project_status "
        "FROM sysadmin_stats s LEFT JOIN projects p ON p.project_id = s.project_id"
    )
    runs = {}
    if 'report_materializations' in present:
        for r in db.run_query(
            "SELECT report_id, status, last_succeeded_at, last_failed_at, duration_ms, error_message "
            "FROM report_materializations WHERE project_id = %(pid)s AND report_id LIKE %(prefix)s",
            {'pid': sysadmin_stats.STAT_PROJECT_ID, 'prefix': sysadmin_stats.REPORT_PREFIX + '%'},
        ):
            runs[r['report_id']] = r
    by_stat = {}
    for r in rows:
        by_stat.setdefault(r['stat_id'], []).append(r)

    jobs = []
    for job_id, job in sysadmin_stats.STAT_JOBS.items():
        stat_ids = list(job['stats'])
        projects = OrderedDict()
        computed_at = None
        for stat_id in stat_ids:
            for r in by_stat.get(stat_id, []):
                p = projects.setdefault(r['project_id'], {
                    'project_id': r['project_id'], 'project_alias': r['project_alias'],
                    'project_title': r['project_title'], 'project_status': r['project_status'],
                    'values': {}})
                p['values'][stat_id] = int(r['value'])
                if computed_at is None or r['computed_at'] > computed_at:
                    computed_at = r['computed_at']
        first = stat_ids[0]
        ordered = sorted(projects.values(), key=lambda p: p['values'].get(first, 0), reverse=True)
        jobs.append({
            'job_id': job_id,
            'title': job['title'],
            'note': job.get('note'),
            'stats': list(job['stats'].items()),
            'projects': ordered,
            'totals': {s: sum(p['values'].get(s, 0) for p in ordered) for s in stat_ids},
            'computed_at': computed_at,
            'run': runs.get(sysadmin_stats.report_id_for(job_id)),
        })
    return {'table_present': True, 'jobs': jobs}
