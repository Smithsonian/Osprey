"""Report read queries shared by the API and dashboard web views."""

import os
import glob
import re
from pathlib import Path
from time import strftime, localtime

import pandas as pd

from logger import logger
from osprey.db import run_query
from osprey.services import builtin_reports
from osprey.services import report_materializations as materializations
from osprey.services import sysadmin_reports

# Pregenerated files of a public report: relative to static/, e.g.
# "reports/report_x_20261013_020000.csv". A sysadmin-only report's files are
# a bare name in sysadmin_reports.ARTIFACT_DIR (see private_artifact_base).
PUBLIC_ARTIFACT_PREFIX = 'reports/'


def is_sysadmin_only(report):
    """True for a data_reports row flagged sysadmin_only.

    Read with .get(): the column comes from db/data_reports_sysadmin_only.sql,
    and until that is applied no report is restricted. Built-in reports have
    no such key and are always public.
    """
    return bool(report and report.get('sysadmin_only'))


def get_report(report_id):
    """Report definition for the API, which never serves sysadmin-only reports."""
    data = run_query(
        "SELECT * FROM data_reports WHERE report_id = %(report_id)s",
        {'report_id': report_id},
    )
    if len(data) == 0:
        data = run_query(
            "SELECT * FROM data_reports WHERE report_alias = %(report_id)s",
            {'report_id': report_id},
        )
    return [row for row in data if not is_sysadmin_only(row)]


def get_project_id(project_alias):
    rows = run_query(
        "SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
        {'project_alias': project_alias},
    )
    return rows[0]['project_id'] if rows else None


def get_project(project_id):
    rows = run_query(
        "SELECT * FROM projects WHERE project_id = %(project_id)s",
        {'project_id': project_id},
    )
    return rows[0] if rows else None


def get_project_report(project_id, report_id):
    rows = run_query(
        ("SELECT *, date_format(updated_at, '%Y-%b-%d %T') as updated_at_f FROM data_reports WHERE "
         " project_id = %(project_id)s AND report_id = %(report_id)s"),
        {'project_id': project_id, 'report_id': report_id},
    )
    if rows:
        return rows[0]
    return builtin_reports.get_builtin_report(project_id, report_id)


def list_project_reports(project_id, include_sysadmin_only=False, include_members_only=False):
    """Per-project data_reports plus built-in reports.

    Sysadmin-only reports are left out unless the caller has checked that the
    viewer is a sysadmin; members-only built-in reports unless the caller has
    checked that the viewer is one of the project's users or an admin.
    """
    reports = builtin_reports.list_project_reports(project_id)
    if not include_sysadmin_only:
        reports = [report for report in reports if not is_sysadmin_only(report)]
    if not include_members_only:
        reports = [report for report in reports if not builtin_reports.is_members_only(report)]
    return reports


def private_artifact_base(project_id, report_id):
    """File name stem of a sysadmin-only report's files in ARTIFACT_DIR.

    The dots keep these apart from sysadmin_reports files, which are named
    after a report_id that cannot contain one.
    """
    safe_id = re.sub(r'[^A-Za-z0-9_-]+', '_', str(report_id))
    return 'data.{}.{}'.format(int(project_id), safe_id)


def artifact_file(report, materialization, fmt):
    """Where the latest csv/xlsx of a pregenerated report can be read from.

    Returns ('static', path under static/), ('private', absolute path), or
    None when there is no file this report may hand out. A sysadmin-only
    report never resolves to static/: files left there by a run from before
    it was restricted are not offered (they go away on its next run).
    """
    name = materialization and materialization.get('artifact_path_' + fmt)
    if not name:
        return None
    if name.startswith(PUBLIC_ARTIFACT_PREFIX):
        return None if is_sysadmin_only(report) else ('static', name)
    stem = private_artifact_base(report['project_id'], report['report_id']) + '_'
    if not name.startswith(stem):
        return None
    path = sysadmin_reports.artifact_path(name)
    return ('private', path) if path else None


def get_report_last_updated(report):
    return run_query(report['query_updated'])[0]['updated_at']


def get_report_data(report):
    """Run a non-pregenerated report's query."""
    return pd.DataFrame(run_query(report['query']))


def get_pregenerated_preview(report, limit=20):
    """Return a small preview DataFrame from the materialized MySQL table.

    Safe for web requests: only fetches ``limit`` rows. Returns None when the
    materialization is missing, not viewable, or the preview query fails.
    """
    mat = get_pregenerated_status(report)
    if not mat:
        return None
    # Allow preview from the last successful materialization even while a
    # refresh is queued/running overnight.
    has_prior_success = mat.get("last_succeeded_at") is not None
    if mat.get("status") != "succeeded" and not has_prior_success:
        return None
    table_name = mat.get("materialized_table_name")
    if not table_name:
        return None
    # Identifiers cannot be parameterized; sanitize like the materializer.
    safe_name = "".join(
        ch if (ch.isalnum() or ch == "_") else "_" for ch in str(table_name)
    )
    if safe_name != str(table_name) or not safe_name:
        return None
    try:
        rows = run_query(
            f"SELECT * FROM `{safe_name}` LIMIT %(limit)s",
            {"limit": int(limit)},
            log_vals=False,
        )
    except Exception:
        logger.exception(
            "get_pregenerated_preview failed for table %s (project_id=%s report_id=%s)",
            safe_name,
            report.get("project_id"),
            report.get("report_id"),
        )
        return None
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def generate_pregenerated_report(report):
    """Return latest completed export artifact paths for a pregenerated report.

    Long-running exports are materialized out-of-band by a scheduler; this
    function must be safe to call inside a web request (no big queries).

    Returns (csv_path, xlsx_path, generated_at_formatted, materialization_row).
    """
    project_id = int(report["project_id"])
    report_id = str(report["report_id"])
    materializations.ensure_row(project_id, report_id)
    mat = materializations.get_materialization(project_id, report_id)
    if not mat:
        return "", "", "", None
    generated_at = mat.get("last_succeeded_at")
    generated_at_formatted = generated_at.strftime("%Y-%m-%d %H:%M:%S") if generated_at else ""
    return (
        mat.get("artifact_path_csv") or "",
        mat.get("artifact_path_xlsx") or "",
        generated_at_formatted,
        mat,
    )


def request_pregenerated_refresh(report, requested_by=None) -> bool:
    """Queue a refresh for a pregenerated report (safe in-request)."""
    project_id = int(report["project_id"])
    report_id = str(report["report_id"])
    materializations.ensure_row(project_id, report_id)
    return materializations.request_refresh(project_id, report_id, requested_by=requested_by)


def get_pregenerated_status(report):
    """Get materialization status row for a pregenerated report."""
    project_id = int(report["project_id"])
    report_id = str(report["report_id"])
    materializations.ensure_row(project_id, report_id)
    return materializations.get_materialization(project_id, report_id)
