"""Transcription grid: fill rate of every field in every folder, with field costs and QC results.

Reads the fill counts the nightly transcription profile already stores in
transcription_profile_fill; nothing is computed from the transcription text here.
"""

from __future__ import annotations

from osprey.db import run_query
from osprey.services.chart_helpers import heat_level, percent, titled


def load_fill_rows(project_id):
    """One row per (source, folder, field), in source, delivery and field order."""
    query = (
        'SELECT p.transcription_source_id AS source_id, s.transcription_source_name AS source_name, '
        '  p.folder_transcription_id AS folder_id, tf.folder AS folder_name, '
        '  p.field_id, p.field_name, p.total_files, p.filled '
        'FROM transcription_profile_fill p '
        'JOIN transcription_sources s ON s.transcription_source_id = p.transcription_source_id '
        'JOIN transcription_folders tf ON tf.folder_transcription_id = p.folder_transcription_id '
        'WHERE p.project_id = %(project_id)s '
        'ORDER BY s.transcription_source_name, p.transcription_source_id, tf.date, tf.folder, '
        '  p.sort_by, p.field_name'
    )
    return run_query(query, {'project_id': project_id})


def load_field_costs(project_id):
    """{field_id: cost per filled field} for the project's sources."""
    rows = run_query(
        'SELECT f.field_id, f.field_cost '
        'FROM transcription_fields f '
        'JOIN transcription_sources s ON s.transcription_source_id = f.transcription_source_id '
        'WHERE s.project_id = %(project_id)s',
        {'project_id': project_id},
    )
    return {row['field_id']: float(row['field_cost']) for row in rows or [] if row.get('field_cost') is not None}


def load_source_qc(project_id):
    """{source_id: {'passed', 'failed', 'pending'}} folder counts from transcription QC."""
    rows = run_query(
        'SELECT q.transcription_source_id AS source_id, '
        '  COALESCE(SUM(q.qc_status = 0), 0) AS passed, '
        '  COALESCE(SUM(q.qc_status = 1), 0) AS failed, '
        '  COALESCE(SUM(q.qc_status = 9), 0) AS pending '
        'FROM transcription_qc_folders q '
        'JOIN transcription_folders tf ON tf.folder_transcription_id = q.folder_transcription_id '
        'WHERE tf.project_id = %(project_id)s '
        'GROUP BY q.transcription_source_id',
        {'project_id': project_id},
    )
    return {
        row['source_id']: {key: int(row[key] or 0) for key in ('passed', 'failed', 'pending')}
        for row in rows or []
    }


def build_transcription_grid_spec(fill_rows, field_costs=None, source_qc=None, *, project_title=''):
    """One folder-by-field grid per source, plus a per-field table with costs."""
    field_costs = field_costs or {}
    source_qc = source_qc or {}

    sources = {}
    for row in fill_rows or []:
        source = sources.setdefault(row['source_id'], {
            'name': row.get('source_name') or str(row['source_id']),
            'fields': {},      # field_id -> {'name', 'total', 'filled'}
            'folders': {},     # folder_id -> {'name', 'cells': {field_id: (filled, total)}}
        })
        total = int(row.get('total_files') or 0)
        filled = int(row.get('filled') or 0)
        field = source['fields'].setdefault(
            row['field_id'], {'name': row.get('field_name') or str(row['field_id']), 'total': 0, 'filled': 0})
        field['total'] += total
        field['filled'] += filled
        folder = source['folders'].setdefault(
            row['folder_id'], {'name': row.get('folder_name') or str(row['folder_id']), 'cells': {}})
        folder['cells'][row['field_id']] = (filled, total)

    grids, table_rows, summary = [], [], []
    for source_id, source in sources.items():
        field_ids = list(source['fields'])
        grid_rows = []
        for folder in source['folders'].values():
            cells = []
            for field_id in field_ids:
                filled, total = folder['cells'].get(field_id, (0, 0))
                pct = percent(filled, total, 0)
                cells.append({
                    'text': f'{pct:.0f}%' if total else '',
                    'level': heat_level(pct, 100) if total else 0,
                    'title': (f"{folder['name']}, {source['fields'][field_id]['name']}: "
                              f'{filled} of {total} file(s) filled'),
                })
            grid_rows.append({'label': folder['name'], 'cells': cells})
        grids.append({
            'title': f"Fill rate by folder and field: {source['name']}",
            'row_header': 'Folder',
            'columns': [source['fields'][field_id]['name'] for field_id in field_ids],
            'rows': grid_rows,
        })

        source_cost = 0.0
        for field_id in field_ids:
            field = source['fields'][field_id]
            cost = field_costs.get(field_id)
            total_cost = round(cost * field['filled'], 2) if cost is not None else ''
            if cost is not None:
                source_cost += cost * field['filled']
            table_rows.append({
                'source': source['name'],
                'field': field['name'],
                'files': field['total'],
                'filled': field['filled'],
                'fill_pct': percent(field['filled'], field['total']),
                'cost_per_field': cost if cost is not None else '',
                'total_cost': total_cost,
            })

        qc = source_qc.get(source_id)
        if qc:
            decided = qc['passed'] + qc['failed']
            value = f"{percent(qc['passed'], decided, 0):.0f}% of {decided} folder(s)" if decided else 'No decisions yet'
            summary.append({'label': f"QC pass rate: {source['name']}", 'value': value})
        if source_cost:
            summary.append({'label': f"Cost of filled fields: {source['name']}", 'value': f'{source_cost:,.2f}'})

    title = titled('Transcription grid', project_title)
    empty = not grids
    if empty:
        short = (f'Grid: {title}. No fill rates stored yet; they are computed overnight '
                 'with the transcription profile.')
    else:
        folders = sum(len(source['folders']) for source in sources.values())
        short = f'Grid: {title}. Fill rate of each field in {folders} folder(s) across {len(sources)} source(s).'

    return {
        'title': title,
        'empty': empty,
        'labels': [],
        'datasets': [],
        'grids': grids,
        'summary': summary,
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'source', 'label': 'Source'},
            {'key': 'field', 'label': 'Field'},
            {'key': 'files', 'label': 'Files'},
            {'key': 'filled', 'label': 'Filled'},
            {'key': 'fill_pct', 'label': '% filled'},
            {'key': 'cost_per_field', 'label': 'Cost per field'},
            {'key': 'total_cost', 'label': 'Cost of filled fields'},
        ],
        'note': ('Darker cells are more complete. Fill rates come from the nightly transcription profile. '
                 'Costs multiply each field\'s cost by the number of files where it was filled.'),
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_transcription_grid_spec(
        load_fill_rows(project_id), load_field_costs(project_id), load_source_qc(project_id),
        project_title=project_title)
