"""Error rate by delivery: share of each folder's files failing each check, in delivery order."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services.chart_helpers import color_at, dataset, iso_day, percent, titled
from osprey.services.file_checks import label_file_check


def load_folder_error_rate_rows(project_id):
    """One row per (folder, failing check); folders with no failures get one row with a NULL check."""
    query = (
        'SELECT fol.folder_id, fol.project_folder, fol.date AS folder_date, '
        '  fol.no_files, fol.no_files_errors, fc.file_check, '
        '  COUNT(DISTINCT fc.file_id) AS error_count '
        'FROM folders fol '
        'LEFT JOIN files_checks fc ON fc.folder_id = fol.folder_id AND fc.check_results = 1 '
        'WHERE fol.project_id = %(project_id)s '
        'GROUP BY fol.folder_id, fol.project_folder, fol.date, fol.no_files, '
        '  fol.no_files_errors, fc.file_check '
        'ORDER BY fol.date, fol.project_folder'
    )
    return run_query(query, {'project_id': project_id})


def build_folder_error_rate_chart_spec(rows, *, project_title=''):
    """Stacked bars: one bar per folder, one segment per failing check (% of the folder's files)."""
    folders = {}
    check_totals = {}
    for row in rows or []:
        folder = folders.setdefault(row['folder_id'], {
            'folder': row.get('project_folder') or str(row['folder_id']),
            'date': iso_day(row.get('folder_date')),
            'files': int(row.get('no_files') or 0),
            'files_with_errors': int(row.get('no_files_errors') or 0),
            'checks': {},
        })
        check = row.get('file_check')
        count = int(row.get('error_count') or 0)
        if check and count:
            folder['checks'][check] = count
            check_totals[check] = check_totals.get(check, 0) + count

    # Most common failure first, so it sits at the bottom of every stack.
    checks = sorted(check_totals, key=lambda name: (-check_totals[name], name))
    ordered = list(folders.values())

    datasets = [
        dataset(label_file_check(check),
                [percent(f['checks'].get(check, 0), f['files'], 2) for f in ordered],
                color_at(i))
        for i, check in enumerate(checks)
    ]

    table_rows = []
    for f in ordered:
        row = {
            'folder': f['folder'],
            'date': f['date'],
            'files': f['files'],
            'files_with_errors': f['files_with_errors'],
            'pct_with_errors': percent(f['files_with_errors'], f['files'], 2),
        }
        for check in checks:
            row['check_' + check] = f['checks'].get(check, 0)
        table_rows.append(row)

    title = titled('Error rate by delivery', project_title)
    empty = not ordered
    if empty:
        short = f'Stacked bar chart: {title}. No folders yet.'
    else:
        with_errors = sum(1 for f in ordered if f['checks'])
        short = (f'Stacked bar chart: {title}. {len(ordered)} folder(s) in delivery order; '
                 f'{with_errors} have files failing at least one check.')

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'stacked': True,
        'units': '% of files',
        'empty': empty,
        'labels': [f['folder'] for f in ordered],
        # With no failures at all, still draw the (flat) axis rather than a blank card.
        'datasets': datasets or [dataset('Files failing checks', [0] * len(ordered), color_at(0))],
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'folder', 'label': 'Folder'},
            {'key': 'date', 'label': 'Folder date'},
            {'key': 'files', 'label': 'Files'},
            {'key': 'files_with_errors', 'label': 'Files with errors'},
            {'key': 'pct_with_errors', 'label': '% with errors'},
        ] + [{'key': 'check_' + check, 'label': label_file_check(check)} for check in checks],
        'note': ('A file that fails two checks is counted in both segments, so a bar can be taller '
                 'than the share of files with errors shown in the data table.'),
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_folder_error_rate_chart_spec(
        load_folder_error_rate_rows(project_id), project_title=project_title)
