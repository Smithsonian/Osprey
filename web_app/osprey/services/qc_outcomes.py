"""QC outcomes over time: each reviewed folder's issue rates against the project's QC limit."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services import qc as qc_service
from osprey.services.chart_helpers import PALETTE, VERMILLION, dataset, iso_day, percent, titled

_QC_RESULT = {0: 'Passed', 1: 'Failed'}
_CRITICAL_COLOR = '#000000'
_MAJOR_COLOR = PALETTE[4]
_MINOR_COLOR = PALETTE[5]


def load_qc_outcome_rows(project_id):
    """One row per image-QC decision, oldest first, with the sampled files' issue counts."""
    query = (
        'SELECT qf.folder_id, fol.project_folder, qf.qc_status, qf.qc_level, qf.qc_method, '
        '  qf.updated_at AS qc_date, '
        '  COUNT(f.table_id) AS sampled, '
        '  COALESCE(SUM(f.file_qc = 1), 0) AS critical, '
        '  COALESCE(SUM(f.file_qc = 2), 0) AS major, '
        '  COALESCE(SUM(f.file_qc = 3), 0) AS minor '
        'FROM qc_folders qf '
        'JOIN folders fol ON fol.folder_id = qf.folder_id '
        'LEFT JOIN qc_files f ON f.folder_id = qf.folder_id '
        'WHERE fol.project_id = %(project_id)s AND qf.qc_status IN (0, 1) '
        'GROUP BY qf.table_id, qf.folder_id, fol.project_folder, qf.qc_status, '
        '  qf.qc_level, qf.qc_method, qf.updated_at '
        'ORDER BY qf.updated_at, qf.table_id'
    )
    return run_query(query, {'project_id': project_id})


def load_qc_settings(project_id):
    rows = run_query('SELECT * FROM qc_settings WHERE project_id = %(project_id)s', {'project_id': project_id})
    return rows[0] if rows else None


def _limit_line(label, value, count):
    """A flat threshold line; its own stack so it is not added to the bars or to other lines."""
    return dataset(label, [value] * count, VERMILLION, type='line', stack='limit',
                   backgroundColor='transparent', borderWidth=2, borderDash=[6, 4],
                   pointRadius=0, fill=False)


def build_qc_outcomes_chart_spec(rows, settings, *, project_title=''):
    """Stacked bars per reviewed folder, with the limit the stack is compared against.

    The stack is built so that its height is what the project's current QC
    method checks: all issues as a share of the sample (cumulative), or the
    weighted major + minor rate (weighted, where critical issues are a
    separate gate and are listed in the data table only).
    """
    rows = list(rows or [])
    method = qc_service.qc_method(settings) if settings else qc_service.QC_METHOD_CUMULATIVE
    weighted = bool(settings) and method == qc_service.QC_METHOD_WEIGHTED
    w_major = float(settings['w_major']) if weighted else 1.0
    w_minor = float(settings['w_minor']) if weighted else 1.0

    labels, critical_pct, major_pct, minor_pct, table_rows = [], [], [], [], []
    for row in rows:
        sampled = int(row.get('sampled') or 0)
        critical, major, minor = (int(row.get(key) or 0) for key in ('critical', 'major', 'minor'))
        labels.append(row.get('project_folder') or str(row.get('folder_id')))
        critical_pct.append(percent(critical, sampled, 3))
        major_pct.append(percent(major * w_major, sampled, 3))
        minor_pct.append(percent(minor * w_minor, sampled, 3))
        table_rows.append({
            'folder': labels[-1],
            'qc_date': iso_day(row.get('qc_date')),
            'result': _QC_RESULT.get(row.get('qc_status'), ''),
            'level': row.get('qc_level') or '',
            'method': row.get('qc_method') or '',
            'sampled': sampled,
            'critical': critical,
            'major': major,
            'minor': minor,
        })

    datasets = []
    if not weighted:
        datasets.append(dataset('Critical', critical_pct, _CRITICAL_COLOR))
    datasets.append(dataset('Major (weighted)' if weighted else 'Major', major_pct, _MAJOR_COLOR))
    datasets.append(dataset('Minor (weighted)' if weighted else 'Minor', minor_pct, _MINOR_COLOR))
    if settings and rows:
        if weighted:
            datasets.append(_limit_line('Weighted rate limit', float(settings['weighted_rate']), len(rows)))
        else:
            datasets.append(_limit_line('Limit for all issues', float(settings['qc_threshold_minor']), len(rows)))

    title = titled('QC outcomes over time', project_title)
    empty = not rows
    if empty:
        short = f'Stacked bar chart: {title}. No folders have been through QC yet.'
    else:
        failed = sum(1 for row in rows if row.get('qc_status') == 1)
        short = (f'Stacked bar chart: {title}. {len(rows)} folder(s) reviewed, {failed} failed, '
                 f'from {table_rows[0]["qc_date"]} to {table_rows[-1]["qc_date"]}.')

    if weighted:
        note = ('Bars show major and minor issues as a share of the sampled files, weighted by the '
                f'project\'s current settings (major x {w_major:g}, minor x {w_minor:g}); the dashed line '
                'is the weighted rate limit. Critical issues are a separate gate and are in the data table.')
    else:
        note = ('Bars show issues as a share of the sampled files; the dashed line is the project\'s '
                'current limit for all issues together.')
    note += ' Each folder\'s recorded result, inspection level and method are in the data table.'

    return {
        'title': title,
        'chart_type': 'bar',
        'chart_js_type': 'bar',
        'stacked': True,
        'units': '% of sample',
        'empty': empty,
        'labels': labels,
        'datasets': datasets,
        'table_rows': table_rows,
        'table_columns': [
            {'key': 'folder', 'label': 'Folder'},
            {'key': 'qc_date', 'label': 'QC date'},
            {'key': 'result', 'label': 'Result'},
            {'key': 'level', 'label': 'Inspection level'},
            {'key': 'method', 'label': 'Method'},
            {'key': 'sampled', 'label': 'Files sampled'},
            {'key': 'critical', 'label': 'Critical'},
            {'key': 'major', 'label': 'Major'},
            {'key': 'minor', 'label': 'Minor'},
        ],
        'note': note,
        'short_description': short,
        'long_description': short,
    }


def load_chart(project_id, *, project_title=''):
    return build_qc_outcomes_chart_spec(
        load_qc_outcome_rows(project_id), load_qc_settings(project_id), project_title=project_title)
