"""File error types: how many files are currently failing each check, per project."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services.file_checks import label_file_check

# Okabe-Ito color: colorblind-safe, matches the "errors" red used elsewhere on the dashboard.
_ERROR_COLOR = '#D55E00'


def load_file_error_type_rows(project_id):
    """Return [{file_check, error_count}, ...] for files currently failing a check."""
    query = (
        'SELECT '
        '  fc.file_check AS file_check, '
        '  COUNT(DISTINCT fc.file_id) AS error_count '
        'FROM files_checks fc '
        'JOIN files f ON f.file_id = fc.file_id '
        'JOIN folders fol ON fol.folder_id = f.folder_id '
        'WHERE fol.project_id = %(project_id)s '
        '  AND fc.check_results = 1 '
        'GROUP BY fc.file_check '
        'ORDER BY error_count DESC, fc.file_check'
    )
    return run_query(query, {'project_id': project_id})


def build_file_error_type_chart_spec(rows, *, project_title=''):
    """Build a one-series bar chart spec (one bar per failing check) for Chart.js."""
    labels = []
    counts = []
    table_rows = []
    for row in rows or []:
        check_name = row.get('file_check')
        if not check_name:
            continue
        count = int(row.get('error_count') or 0)
        label = label_file_check(check_name)
        labels.append(label)
        counts.append(count)
        table_rows.append({'check': label, 'count': count})

    title = 'File error types'
    if project_title:
        title = f'{title} for {project_title}'

    empty = not labels
    if empty:
        short = f'Bar chart: {title}. No files currently have errors.'
    else:
        short = (
            f'Bar chart: {title}. {len(labels)} check type(s) failing on '
            f'{sum(counts)} file check(s) total.'
        )

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'units': 'files',
        'empty': empty,
        'labels': labels,
        'datasets': [
            {
                'label': 'Files with errors',
                'data': counts,
                'backgroundColor': _ERROR_COLOR,
                'borderColor': _ERROR_COLOR,
                'borderWidth': 1,
            },
        ],
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'check', 'label': 'Error type'},
            {'key': 'count', 'label': 'Files'},
        ],
        'short_description': short,
        'long_description': short,
    }
