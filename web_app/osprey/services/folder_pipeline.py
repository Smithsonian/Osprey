"""Folder pipeline: how many of a project's folders sit at each stage, and for how long."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services.chart_helpers import BLUE, GREEN, VERMILLION, dataset, five_numbers, titled

# (key, label, bar color), in pipeline order.
STAGES = [
    ('errors', 'File errors', VERMILLION),
    ('checking', 'Being checked', BLUE),
    ('awaiting_qc', 'Waiting for QC', BLUE),
    ('qc_failed', 'QC failed', VERMILLION),
    ('qc_passed', 'QC passed', BLUE),
    ('ready_dams', 'Ready for DAMS', BLUE),
    ('in_dams', 'In DAMS', GREEN),
]


def folder_stage(row):
    """The furthest pipeline stage a folder has reached.

    Status codes: 0 = OK/done, 1 = error (or, for delivered_to_dams, ready), 9 = pending.
    """
    dams = row.get('delivered_to_dams')
    qc = row.get('qc_status')
    if dams == 0:
        return 'in_dams'
    if dams == 1:
        return 'ready_dams'
    if qc == 0:
        return 'qc_passed'
    if qc == 1:
        return 'qc_failed'
    if row.get('status') == 1 or row.get('file_errors') == 1:
        return 'errors'
    if row.get('status') == 0:
        return 'awaiting_qc'
    return 'checking'


def load_folder_pipeline_rows(project_id):
    """One row per folder with its status columns and days since it last changed."""
    query = (
        'SELECT f.folder_id, f.project_folder, f.status, f.file_errors, '
        '  f.delivered_to_dams, f.no_files, q.qc_status, '
        '  DATEDIFF(CURRENT_DATE, GREATEST(f.updated_at, COALESCE(q.updated_at, f.updated_at))) '
        '    AS days_since_change '
        'FROM folders f '
        'LEFT JOIN qc_folders q ON q.folder_id = f.folder_id '
        'WHERE f.project_id = %(project_id)s '
        'ORDER BY f.folder_id, q.updated_at DESC'
    )
    rows = run_query(query, {'project_id': project_id})
    # A folder with several qc_folders rows keeps only its latest decision.
    latest = {}
    for row in rows or []:
        latest.setdefault(row['folder_id'], row)
    return list(latest.values())


def build_folder_pipeline_chart_spec(rows, *, project_title=''):
    """Bar chart of folders per stage, with waiting times in the data table."""
    by_stage = {key: [] for key, _, _ in STAGES}
    for row in rows or []:
        by_stage[folder_stage(row)].append(row)

    table_rows = []
    for key, label, _ in STAGES:
        folders = by_stage[key]
        waits = [int(r['days_since_change']) for r in folders if r.get('days_since_change') is not None]
        stats = five_numbers(waits, digits=0)
        oldest = max(folders, key=lambda r: r.get('days_since_change') or 0) if folders else None
        # Folders in DAMS are finished, so how long ago they changed is not a wait.
        waiting = key != 'in_dams' and stats is not None
        table_rows.append({
            'stage': label,
            'folders': len(folders),
            'files': sum(int(r.get('no_files') or 0) for r in folders),
            'median_days': int(stats['median']) if waiting else '',
            'max_days': int(stats['max']) if waiting else '',
            'oldest_folder': oldest.get('project_folder') or '' if waiting else '',
        })

    title = titled('Folder pipeline', project_title)
    total = sum(row['folders'] for row in table_rows)
    empty = total == 0
    if empty:
        short = f'Bar chart: {title}. No folders yet.'
    else:
        parts = ', '.join(f"{row['folders']} {row['stage'].lower()}" for row in table_rows if row['folders'])
        short = f'Bar chart: {title}. {total} folder(s): {parts}.'

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'units': 'folders',
        'empty': empty,
        'labels': [label for _, label, _ in STAGES],
        'datasets': [dataset('Folders', [row['folders'] for row in table_rows],
                             [color for _, _, color in STAGES])],
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'stage', 'label': 'Stage'},
            {'key': 'folders', 'label': 'Folders'},
            {'key': 'files', 'label': 'Files'},
            {'key': 'median_days', 'label': 'Median days since last change'},
            {'key': 'max_days', 'label': 'Longest (days)'},
            {'key': 'oldest_folder', 'label': 'Folder waiting longest'},
        ],
        'note': ('Each folder is counted once, at the furthest stage it has reached. '
                 'Days are counted from the last change recorded for the folder or its QC.'),
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_folder_pipeline_chart_spec(load_folder_pipeline_rows(project_id), project_title=project_title)
