"""Report read queries shared by the API and dashboard web views."""

import os
import glob
from pathlib import Path
from time import strftime, localtime

import pandas as pd

from osprey.db import run_query


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
    """Delete stale cached exports and regenerate CSV/XLSX for a pregenerated report.

    Returns (report_dataframe, csv_path, xlsx_path, generated_at_formatted).
    """
    for ext in ('csv', 'xlsx'):
        files_todel = glob.glob("static/reports/{}_*.{}".format(report['pregen_filename'], ext))
        for file in files_todel:
            try:
                os.remove(file)
            except FileNotFoundError:
                continue
    Path("static/reports").mkdir(parents=True, exist_ok=True)
    rep_timestamp = localtime()
    current_datetime = strftime("%Y%m%d_%H%M%S", rep_timestamp)
    current_datetime_formatted = strftime("%Y-%m-%d %H:%M:%S", rep_timestamp)
    report_data = pd.DataFrame(run_query(report['query']))
    data_file = "reports/{}_{}.csv".format(report['pregen_filename'], current_datetime)
    report_data.to_csv("static/{}".format(data_file), index=False)
    data_file_e = "reports/{}_{}.xlsx".format(report['pregen_filename'], current_datetime)
    report_data.to_excel("static/{}".format(data_file_e), index=False)
    return report_data, data_file, data_file_e, current_datetime_formatted
