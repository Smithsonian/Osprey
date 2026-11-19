"""Storage growth: cumulative size on disk by file type, folder by folder."""

from __future__ import annotations

from datetime import date

from osprey.db import run_query
from osprey.services.chart_helpers import color_at, dataset, iso_day, titled

_GB = 1024 ** 3
_MB = 1024 ** 2


def load_storage_rows(project_id):
    """One row per (folder, file type) with its file count and total bytes, in delivery order."""
    query = (
        'SELECT fol.folder_id, fol.project_folder, fol.date AS folder_date, '
        '  UPPER(fs.filetype) AS filetype, COUNT(*) AS files, '
        # filesize is stored as text
        '  SUM(CAST(fs.filesize AS UNSIGNED)) AS bytes '
        'FROM files_size fs '
        'JOIN files f ON f.file_id = fs.file_id '
        'JOIN folders fol ON fol.folder_id = f.folder_id '
        'WHERE fol.project_id = %(project_id)s '
        'GROUP BY fol.folder_id, fol.project_folder, fol.date, UPPER(fs.filetype) '
        'ORDER BY fol.date, fol.project_folder, filetype'
    )
    return run_query(query, {'project_id': project_id})


def pick_time_unit(first_day, last_day):
    """Chart.js time unit that keeps the date axis readable for this span."""
    days = (date.fromisoformat(last_day) - date.fromisoformat(first_day)).days
    if days <= 92:
        return 'day'
    if days <= 3 * 366:
        return 'month'
    return 'year'


def build_storage_growth_chart_spec(rows, *, project_title=''):
    """Line chart of cumulative GB per file type over folder dates; per-folder sizes in the table.

    The x axis is folders.date. Folders sharing a date are added together into
    one point; folders with no date are listed in the table but left off the chart.
    """
    per_day = {}           # (iso date, filetype) -> bytes
    filetypes = []
    undated = set()
    table_rows = []
    for row in rows or []:
        folder_id = row['folder_id']
        day = iso_day(row.get('folder_date'))
        filetype = row.get('filetype') or 'UNKNOWN'
        size = int(row.get('bytes') or 0)
        files = int(row.get('files') or 0)
        if filetype not in filetypes:
            filetypes.append(filetype)
        if day:
            per_day[(day, filetype)] = per_day.get((day, filetype), 0) + size
        else:
            undated.add(folder_id)
        table_rows.append({
            'folder': row.get('project_folder') or str(folder_id),
            'date': day,
            'filetype': filetype,
            'files': files,
            'gb': round(size / _GB, 3),
            'avg_mb': round(size / files / _MB, 1) if files else '',
        })

    days = sorted({day for day, _ in per_day})
    filetypes.sort()
    datasets = []
    totals = {}
    for i, filetype in enumerate(filetypes):
        running = 0
        points = []
        for day in days:
            running += per_day.get((day, filetype), 0)
            points.append({'x': day, 'y': round(running / _GB, 2)})
        totals[filetype] = running
        datasets.append(dataset(filetype, points, color_at(i), fill=False, tension=0, pointRadius=2))

    title = titled('Storage growth', project_title)
    empty = not days
    if not table_rows:
        short = f'Line chart: {title}. No file sizes recorded yet.'
    elif empty:
        short = f'Line chart: {title}. No folder with recorded file sizes has a date.'
    else:
        parts = ', '.join(f'{ft} {totals[ft] / _GB:,.1f} GB' for ft in filetypes)
        short = f'Time series line chart: {title}. Cumulative size from {days[0]} to {days[-1]}: {parts}.'

    note = ('Each point adds up the folders dated that day. A jump in average file size between '
            'folders usually means the capture or compression settings changed.')
    if undated:
        note += (f' {len(undated)} folder(s) have no date: they are in the data table but not on the chart, '
                 'so the line ends below the full total.')

    return {
        'title': title,
        'chart_type': 'line',
        'chart_js_type': 'line',
        'x_scale': 'time',
        'time_unit': pick_time_unit(days[0], days[-1]) if days else 'day',
        'units': 'GB',
        'empty': empty,
        'labels': days,
        'datasets': datasets,
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'folder', 'label': 'Folder'},
            {'key': 'date', 'label': 'Folder date'},
            {'key': 'filetype', 'label': 'File type'},
            {'key': 'files', 'label': 'Files'},
            {'key': 'gb', 'label': 'Size (GB)'},
            {'key': 'avg_mb', 'label': 'Average file size (MB)'},
        ],
        'note': note,
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_storage_growth_chart_spec(load_storage_rows(project_id), project_title=project_title)
