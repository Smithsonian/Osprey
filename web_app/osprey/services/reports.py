"""Report read queries shared by the API."""

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
