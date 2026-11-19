"""Turnaround times: days each folder took between capture, delivery, QC and DAMS ingest."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services.chart_helpers import BLUE, dataset, five_numbers, titled

# (label, start key, end key) for each hand-off.
HANDOFFS = [
    ('Capture to delivery', 'captured', 'delivered'),
    ('Delivery to QC decision', 'delivered', 'qc_decided'),
    ('QC decision to DAMS', 'qc_decided', 'in_dams'),
]


def load_folder_milestones(project_id):
    """{folder_id: {captured, delivered, qc_decided, in_dams}} (datetimes; missing ones absent).

    captured = earliest EXIF capture date of the folder's files; delivered =
    when its first file was registered by the worker; qc_decided = when the
    folder passed or failed QC; in_dams = first DAMS ingest of one of its files.
    """
    params = {'project_id': project_id}
    milestones = {}

    for row in run_query(
            'SELECT f.folder_id, MIN(f.datetime_created) AS captured, MIN(f.created_at) AS delivered '
            'FROM files f JOIN folders fol ON fol.folder_id = f.folder_id '
            'WHERE fol.project_id = %(project_id)s '
            'GROUP BY f.folder_id', params) or []:
        milestones[row['folder_id']] = {'captured': row.get('captured'), 'delivered': row.get('delivered')}

    for row in run_query(
            'SELECT qf.folder_id, MAX(qf.updated_at) AS qc_decided '
            'FROM qc_folders qf JOIN folders fol ON fol.folder_id = qf.folder_id '
            'WHERE fol.project_id = %(project_id)s AND qf.qc_status IN (0, 1) '
            'GROUP BY qf.folder_id', params) or []:
        milestones.setdefault(row['folder_id'], {})['qc_decided'] = row.get('qc_decided')

    for row in run_query(
            'SELECT f.folder_id, MIN(d.to_dams_ingest_dt) AS in_dams '
            'FROM files f '
            'JOIN folders fol ON fol.folder_id = f.folder_id '
            'JOIN dams_cdis_file_status_view_dpo d ON d.dams_uan = f.dams_uan '
            'WHERE fol.project_id = %(project_id)s AND f.dams_uan IS NOT NULL '
            'GROUP BY f.folder_id', params) or []:
        milestones.setdefault(row['folder_id'], {})['in_dams'] = row.get('in_dams')

    return milestones


def _days_between(start, end):
    if start is None or end is None:
        return None
    days = (end - start).total_seconds() / 86400
    # A negative gap means the clocks or the steps were out of order; it is not a turnaround.
    return days if days >= 0 else None


def build_turnaround_chart_spec(milestones, *, project_title=''):
    """Median days per hand-off as bars; the full spread (min, quartiles, max) in the table."""
    table_rows = []
    for label, start_key, end_key in HANDOFFS:
        days = [
            gap for gap in (
                _days_between(m.get(start_key), m.get(end_key)) for m in (milestones or {}).values()
            ) if gap is not None
        ]
        stats = five_numbers(days) or {'n': 0, 'min': '', 'q1': '', 'median': '', 'q3': '', 'max': ''}
        table_rows.append(dict(stats, handoff=label))

    title = titled('Turnaround times', project_title)
    empty = all(row['n'] == 0 for row in table_rows)
    if empty:
        short = f'Bar chart: {title}. No folders have dates for any hand-off yet.'
    else:
        parts = '; '.join(
            f"{row['handoff'].lower()}: median {row['median']} day(s) over {row['n']} folder(s)"
            for row in table_rows if row['n'])
        short = f'Bar chart: {title}. {parts}.'

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'units': 'days',
        'empty': empty,
        'labels': [row['handoff'] for row in table_rows],
        'datasets': [dataset('Median days', [row['median'] or 0 for row in table_rows], BLUE)],
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'handoff', 'label': 'Hand-off'},
            {'key': 'n', 'label': 'Folders'},
            {'key': 'min', 'label': 'Shortest (days)'},
            {'key': 'q1', 'label': 'Lower quartile'},
            {'key': 'median', 'label': 'Median'},
            {'key': 'q3', 'label': 'Upper quartile'},
            {'key': 'max', 'label': 'Longest (days)'},
        ],
        'note': ('Measured per folder: capture is the earliest capture date in its files, delivery is '
                 'when its first file was registered, and DAMS is the first ingest of one of its files. '
                 'Folders missing either date of a hand-off are left out of it.'),
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_turnaround_chart_spec(load_folder_milestones(project_id), project_title=project_title)
