"""Reviewer workload: folders each QC reviewer decided per week, and the queue waiting for QC."""

from __future__ import annotations

from datetime import date, timedelta

from osprey.db import run_query
from osprey.services.chart_helpers import color_at, dataset, iso_day, titled


def load_reviewer_rows(project_id):
    """One row per (week, reviewer): folders decided and files rated that week."""
    query = (
        'SELECT DATE(DATE_SUB(qf.updated_at, INTERVAL WEEKDAY(qf.updated_at) DAY)) AS week_start, '
        "  COALESCE(u.full_name, u.username, 'Unknown') AS reviewer, "
        '  COUNT(DISTINCT qf.folder_id) AS folders, '
        '  COUNT(f.table_id) AS files '
        'FROM qc_folders qf '
        'JOIN folders fol ON fol.folder_id = qf.folder_id '
        'LEFT JOIN users u ON u.user_id = qf.qc_by '
        'LEFT JOIN qc_files f ON f.folder_id = qf.folder_id '
        'WHERE fol.project_id = %(project_id)s AND qf.qc_status IN (0, 1) '
        'GROUP BY week_start, reviewer '
        'ORDER BY week_start, reviewer'
    )
    return run_query(query, {'project_id': project_id})


def load_pending_folders(project_id):
    """Folders whose file checks are done but that have no QC decision yet."""
    rows = run_query(
        'SELECT COUNT(DISTINCT fol.folder_id) AS pending '
        'FROM folders fol '
        'LEFT JOIN qc_folders qf ON qf.folder_id = fol.folder_id '
        'WHERE fol.project_id = %(project_id)s AND fol.status = 0 '
        '  AND (qf.qc_status IS NULL OR qf.qc_status = 9)',
        {'project_id': project_id},
    )
    return int(rows[0]['pending'] or 0) if rows else 0


def build_reviewer_workload_chart_spec(rows, pending=0, *, project_title=''):
    """Stacked bars per week, one segment per reviewer (folders decided)."""
    by_week = {}
    reviewers = []
    table_rows = []
    for row in rows or []:
        week = iso_day(row.get('week_start'))
        if not week:
            continue
        reviewer = row.get('reviewer') or 'Unknown'
        folders = int(row.get('folders') or 0)
        if reviewer not in reviewers:
            reviewers.append(reviewer)
        by_week.setdefault(week, {})[reviewer] = folders
        table_rows.append({
            'week': week,
            'reviewer': reviewer,
            'folders': folders,
            'files': int(row.get('files') or 0),
        })

    # Weeks with no QC at all are part of the picture, so fill them in.
    weeks = []
    if by_week:
        week = date.fromisoformat(min(by_week))
        last = date.fromisoformat(max(by_week))
        while week <= last:
            weeks.append(week.isoformat())
            week += timedelta(weeks=1)

    reviewers.sort()
    datasets = [
        dataset(reviewer, [by_week.get(week, {}).get(reviewer, 0) for week in weeks], color_at(i))
        for i, reviewer in enumerate(reviewers)
    ]

    title = titled('Reviewer workload', project_title)
    empty = not weeks and not pending
    total = sum(row['folders'] for row in table_rows)
    if not weeks:
        short = f'Stacked bar chart: {title}. No QC decisions yet; {pending} folder(s) waiting for QC.'
    else:
        short = (f'Stacked bar chart: {title}. {total} folder decision(s) by {len(reviewers)} reviewer(s) '
                 f'over {len(weeks)} week(s) from {weeks[0]}; {pending} folder(s) waiting for QC now.')

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'stacked': True,
        'units': 'folders',
        'empty': empty,
        'labels': weeks,
        'datasets': datasets,
        'summary': [
            {'label': 'Folders waiting for QC', 'value': pending},
            {'label': 'Folder decisions recorded', 'value': total},
        ],
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'week', 'label': 'Week starting'},
            {'key': 'reviewer', 'label': 'Reviewer'},
            {'key': 'folders', 'label': 'Folders decided'},
            {'key': 'files', 'label': 'Files rated'},
        ],
        'note': 'A decision is counted in the week of the latest change to the folder\'s QC record.',
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_reviewer_workload_chart_spec(
        load_reviewer_rows(project_id), load_pending_folders(project_id), project_title=project_title)
