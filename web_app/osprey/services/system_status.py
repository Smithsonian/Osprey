"""Read-only system status for the sysadmin page.

Every section is collected independently: a failure in one (DB down, log
file unreadable) is logged and reported in that section instead of failing
the whole page, since this page is most useful exactly when something is
broken.
"""

import os
import platform
import time
from importlib import metadata

import settings
from cache import cache
from logger import api_logger, app_log_handler, logger
from osprey import db
from osprey.version import __version__ as site_ver

# How much of the end of each log file to scan for errors. Bounded so a large
# log never turns a page load into a full-file read.
LOG_TAIL_BYTES = 256 * 1024
LOG_MAX_LINES = 50
LOG_LEVELS = ('ERROR |', 'CRITICAL |')

# Packages whose installed version is worth seeing at a glance.
PACKAGES = ('flask', 'flask-login', 'Flask-WTF', 'Flask-Caching',
            'mysql-connector-python', 'pandas', 'ldap3')

# MySQL "table doesn't exist": report_materializations is applied by hand
# (db/report_materializations.sql), so it may legitimately be missing.
ER_NO_SUCH_TABLE = 1146


def _section(name, func):
    """Run one collector; on failure log it and return an error marker."""
    try:
        return {'ok': True, 'data': func()}
    except Exception as err:  # boundary: DB, file I/O; logged, shown on page
        logger.exception("sysadmin status: {} failed".format(name))
        return {'ok': False, 'error': "{}: {}".format(type(err).__name__, err)}


def app_info():
    versions = {}
    for pkg in PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = 'not installed'
    return {
        'version': site_ver,
        'env': settings.env,
        'site_net': settings.site_net,
        'python': platform.python_version(),
        'host': platform.node(),
        'packages': versions,
    }


def db_info():
    start = time.monotonic()
    rows = db.run_query("SELECT VERSION() AS version, NOW() AS db_now")
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return {
        'server_version': rows[0]['version'],
        'db_now': rows[0]['db_now'],
        'latency_ms': latency_ms,
        'pool_size': db.POOL_SIZE,
        'database': settings.database,
        'host': settings.host,
    }


def cache_info():
    # The resolved directory cache.py actually configured, not settings'
    # possibly-relative value.
    cache_dir = cache.config['CACHE_DIR']
    files = 0
    total = 0
    with os.scandir(cache_dir) as it:
        for entry in it:
            if entry.is_file(follow_symlinks=False):
                files += 1
                total += entry.stat(follow_symlinks=False).st_size
    return {'dir': cache_dir, 'files': files, 'bytes': total}


def reports_info():
    try:
        by_status = db.run_query(
            "SELECT status, COUNT(*) AS n, MAX(updated_at) AS last_update "
            "FROM report_materializations GROUP BY status ORDER BY status"
        )
    except Exception as err:
        if getattr(err, 'errno', None) == ER_NO_SUCH_TABLE:
            return {'table_present': False}
        raise
    summary = db.run_query(
        "SELECT MAX(last_succeeded_at) AS last_success, "
        "  SUM(CASE WHEN last_succeeded_at IS NULL "
        "        OR last_succeeded_at < NOW() - INTERVAL freshness_sla_seconds SECOND "
        "      THEN 1 ELSE 0 END) AS stale "
        "FROM report_materializations"
    )
    failures = db.run_query(
        "SELECT project_id, report_id, last_failed_at, "
        "  LEFT(error_message, 300) AS error_message "
        "FROM report_materializations WHERE status = 'failed' "
        "ORDER BY last_failed_at DESC LIMIT 10"
    )
    return {
        'table_present': True,
        'by_status': by_status,
        'last_success': summary[0]['last_success'] if summary else None,
        'stale': int(summary[0]['stale'] or 0) if summary else 0,
        'failures': failures,
    }


def _tail_errors(path):
    """Last ERROR/CRITICAL lines from the end of a log file."""
    if not os.path.exists(path):
        # delay=True handlers only create the file on first write.
        return {'path': path, 'exists': False, 'lines': []}
    with open(path, 'rb') as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - LOG_TAIL_BYTES))
        chunk = fh.read().decode('utf-8', errors='replace')
    lines = [ln for ln in chunk.splitlines() if ln.startswith(LOG_LEVELS)]
    return {'path': path, 'exists': True, 'size': size,
            'lines': lines[-LOG_MAX_LINES:][::-1]}


def log_info():
    paths = [app_log_handler.baseFilename]
    paths += [h.baseFilename for h in api_logger.handlers if hasattr(h, 'baseFilename')]
    return [_tail_errors(p) for p in paths]


def collect():
    return {
        'app': _section('app', app_info),
        'db': _section('db', db_info),
        'cache': _section('cache', cache_info),
        'reports': _section('reports', reports_info),
        'logs': _section('logs', log_info),
    }
