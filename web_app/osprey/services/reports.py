"""Report read queries shared by the API and dashboard web views."""

import os
import glob
from pathlib import Path
from time import strftime, localtime

import pandas as pd

from osprey.db import run_query
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
    return rows[0] if rows else None


def get_report_last_updated(report):
    return run_query(report['query_updated'])[0]['updated_at']


def get_report_data(report):
    """Run a non-pregenerated report's query."""
    return pd.DataFrame(run_query(report['query']))


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
