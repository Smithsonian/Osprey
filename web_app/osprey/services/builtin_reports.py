"""Built-in reports available for every project without a data_reports row."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services import daily_throughput

BUILTIN_REPORT_DEFS = {
    'daily_throughput': {
        'report_id': 'daily_throughput',
        'report_title': 'Daily throughput',
        'report_title_brief': 'Daily throughput',
        'render': 'chart',
        'pregenerated': 0,
        'builtin': 1,
    },
}


def _builtin_row(project_id, report_id):
    meta = BUILTIN_REPORT_DEFS.get(report_id)
    if meta is None:
        return None
    row = dict(meta)
    row['project_id'] = project_id
    return row


def get_builtin_report(project_id, report_id):
    """Return a synthetic data_reports-shaped row for a built-in report."""
    return _builtin_row(project_id, report_id)


def list_builtin_reports(project_id):
    """All built-in reports for a project."""
    return [_builtin_row(project_id, rid) for rid in sorted(BUILTIN_REPORT_DEFS)]


def list_project_reports(project_id):
    """Merge per-project data_reports rows with built-in reports (DB wins on id clash)."""
    rows = run_query(
        'SELECT * FROM data_reports WHERE project_id = %(project_id)s ORDER BY report_id',
        {'project_id': project_id},
    )
    db_ids = {str(row['report_id']) for row in rows}
    builtins = [
        row for row in list_builtin_reports(project_id)
        if str(row['report_id']) not in db_ids
    ]
    return rows + builtins


def is_builtin_chart_report(report):
    return bool(report and report.get('builtin') and report.get('render') == 'chart')


def chart_spec_for_js(spec):
    """Return a JSON-serializable Chart.js payload with safe defaults."""
    js_spec = {
        'step_id': spec.get('step_id') or '',
        'chart_js_type': spec.get('chart_js_type') or 'bar',
        'chart_type': spec.get('chart_type') or 'bar',
        'labels': spec.get('labels') or [],
        'datasets': spec.get('datasets') or [],
        'units': spec.get('units') or '',
        'title': spec.get('title') or '',
    }
    x_scale = spec.get('x_scale')
    if x_scale:
        js_spec['x_scale'] = x_scale
        time_unit = spec.get('time_unit')
        if time_unit:
            js_spec['time_unit'] = time_unit
    return js_spec


def load_chart_report(project_id, report_id, *, project_title=''):
    """Load chart spec for a built-in chart report."""
    if report_id == 'daily_throughput':
        rows = daily_throughput.load_daily_throughput_rows(project_id)
        spec = daily_throughput.build_daily_throughput_chart_spec(
            rows, project_title=project_title,
        )
        spec['step_id'] = report_id
        spec['chart_js_spec'] = chart_spec_for_js(spec)
        return spec
    raise ValueError(f'Unknown built-in chart report: {report_id}')
