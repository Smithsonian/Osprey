"""Report read queries shared by the API and dashboard web views."""

import os
import glob
from pathlib import Path
from time import strftime, localtime

import pandas as pd

from logger import logger
from osprey.db import run_query
from osprey.services import builtin_reports
from osprey.services import report_materializations as materializations


def get_report(report_id):
    data = run_query(
        "SELECT * FROM data_reports WHERE report_id = %(report_id)s",
        {'report_id': report_id},
    )
    if len(data) == 0:
        data = run_query(
            "SELECT * FROM data_reports WHERE report_alias = %(report_id)s",
            {'report_id': report_id},
        )
    return data


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


def list_project_reports(project_id):
    """Per-project data_reports plus built-in reports."""
    return builtin_reports.list_project_reports(project_id)


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
    if rows is False:
        logger.error(
            "get_pregenerated_preview query returned error for table %s "
            "(project_id=%s report_id=%s)",
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
