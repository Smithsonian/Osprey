"""Built-in reports available for every project without a data_reports row."""

from __future__ import annotations

from osprey.db import run_query
from osprey.services import capture_calendar
from osprey.services import daily_throughput
from osprey.services import file_error_types
from osprey.services import folder_error_rates
from osprey.services import folder_pipeline
from osprey.services import qc_outcomes
from osprey.services import reviewer_workload
from osprey.services import storage_growth
from osprey.services import transcription_grid
from osprey.services import turnaround_times


# Dashboard report menus, in display order: (key, label, Font Awesome icon).
# Reports without a category (the project's own data_reports rows) go in the last one.
REPORT_CATEGORIES = [
    ('production', 'Production', 'fa-camera'),
    ('quality', 'Quality', 'fa-clipboard-check'),
    ('workflow', 'Workflow', 'fa-diagram-project'),
    ('project_data', 'Project data', 'fa-table'),
]
DEFAULT_CATEGORY = 'project_data'


def _chart_def(report_id, title, brief=None, **flags):
    """A built-in chart report definition (data_reports-shaped)."""
    row = {
        'report_id': report_id,
        'report_title': title,
        'report_title_brief': brief or title,
        'render': 'chart',
        'pregenerated': 0,
        'builtin': 1,
    }
    row.update(flags)
    return row


BUILTIN_REPORT_DEFS = {
    'daily_throughput': _chart_def('daily_throughput', 'Daily throughput', category='production'),
    'file_error_types': _chart_def('file_error_types', 'File error types', 'Error types', category='quality'),
    'folder_pipeline': _chart_def('folder_pipeline', 'Folder pipeline', category='workflow'),
    'folder_error_rates': _chart_def('folder_error_rates', 'Error rate by delivery', 'Error rate', category='quality'),
    'turnaround_times': _chart_def('turnaround_times', 'Turnaround times', 'Turnaround', category='workflow'),
    'capture_calendar': _chart_def('capture_calendar', 'Capture calendar', category='production'),
    'storage_growth': _chart_def('storage_growth', 'Storage growth', category='production'),
    # members_only: names QC results and reviewers, so only the project's
    # users (qc_projects) and admins see it; everyone else gets a 404.
    'qc_outcomes': _chart_def('qc_outcomes', 'QC outcomes over time', 'QC outcomes', members_only=True, category='quality'),
    'reviewer_workload': _chart_def('reviewer_workload', 'Reviewer workload', members_only=True, category='workflow'),
    'transcription_grid': _chart_def('transcription_grid', 'Transcription grid', transcription_only=True, category='project_data'),
    # Computed overnight by scripts/materialize_reports.py, hence pregenerated=1
    # (also enables the existing /refresh and /status endpoints).
    'transcription_profile': {
        'report_id': 'transcription_profile',
        'report_title': 'Transcription profile',
        'report_title_brief': 'Transcription profile',
        'render': 'transcription_profile',
        'pregenerated': 1,
        'builtin': 1,
        'transcription_only': True,
        'category': 'project_data',
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


def _is_transcription_project(project_id):
    rows = run_query(
        'SELECT transcription FROM projects WHERE project_id = %(project_id)s',
        {'project_id': project_id},
    )
    return bool(rows) and rows[0]['transcription'] == 1


def list_builtin_reports(project_id):
    """All built-in reports for a project (transcription-only ones only for transcription projects)."""
    rows = [_builtin_row(project_id, rid) for rid in sorted(BUILTIN_REPORT_DEFS)]
    if not _is_transcription_project(project_id):
        rows = [row for row in rows if not row.get('transcription_only')]
    return rows


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


def is_members_only(report):
    """True for a built-in report limited to the project's users and admins."""
    return bool(report and report.get('members_only'))


def report_kind(report):
    """(icon, label) for what kind of report this is, shown in the dashboard menus."""
    if report.get('render') == 'transcription_profile':
        return 'fa-moon', 'Updated nightly'
    if report.get('builtin'):
        return 'fa-chart-column', 'Chart'
    if int(report.get('pregenerated') or 0) == 1:
        return 'fa-file-arrow-down', 'Export file'
    return 'fa-table-list', 'Live table'


def report_access_label(report):
    """Who may see a restricted report ('' for everyone)."""
    if report.get('sysadmin_only'):
        return 'Sysadmin only'
    if is_members_only(report):
        return 'Project team only'
    return ''


def group_reports(reports):
    """Reports grouped for the dashboard menus: [{key, label, icon, reports}], empty groups left out.

    Each report gains kind_icon, kind_label and access_label; reports keep
    their order within a group.
    """
    known = {key for key, _, _ in REPORT_CATEGORIES}
    grouped = {key: [] for key in known}
    for report in reports or []:
        category = report.get('category')
        if category not in known:
            category = DEFAULT_CATEGORY
        kind_icon, kind_label = report_kind(report)
        grouped[category].append(dict(
            report, kind_icon=kind_icon, kind_label=kind_label, access_label=report_access_label(report)))
    return [
        {'key': key, 'label': label, 'icon': icon, 'reports': grouped[key]}
        for key, label, icon in REPORT_CATEGORIES if grouped[key]
    ]


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
    # Optional layout switches read by static/js/statistics_charts.js
    if spec.get('stacked'):
        js_spec['stacked'] = True
    if spec.get('index_axis'):
        js_spec['index_axis'] = spec['index_axis']
    x_scale = spec.get('x_scale')
    if x_scale:
        js_spec['x_scale'] = x_scale
        time_unit = spec.get('time_unit')
        if time_unit:
            js_spec['time_unit'] = time_unit
    return js_spec


def _load_daily_throughput(project_id, *, project_title=''):
    rows = daily_throughput.load_daily_throughput_rows(project_id)
    return daily_throughput.build_daily_throughput_chart_spec(rows, project_title=project_title)


def _load_file_error_types(project_id, *, project_title=''):
    rows = file_error_types.load_file_error_type_rows(project_id)
    return file_error_types.build_file_error_type_chart_spec(rows, project_title=project_title)


# report_id -> loader(project_id, *, project_title) returning a chart spec
CHART_LOADERS = {
    'daily_throughput': _load_daily_throughput,
    'file_error_types': _load_file_error_types,
    'folder_pipeline': folder_pipeline.load_chart,
    'folder_error_rates': folder_error_rates.load_chart,
    'turnaround_times': turnaround_times.load_chart,
    'capture_calendar': capture_calendar.load_chart,
    'storage_growth': storage_growth.load_chart,
    'qc_outcomes': qc_outcomes.load_chart,
    'reviewer_workload': reviewer_workload.load_chart,
    'transcription_grid': transcription_grid.load_chart,
}


def finish_chart_spec(spec, chart_id):
    """Add the id and the Chart.js payload the chart card template needs."""
    spec['step_id'] = chart_id
    spec['chart_js_spec'] = chart_spec_for_js(spec)
    return spec


def load_chart_report(project_id, report_id, *, project_title=''):
    """Load chart spec for a built-in chart report."""
    loader = CHART_LOADERS.get(report_id)
    if loader is None:
        raise ValueError(f'Unknown built-in chart report: {report_id}')
    return finish_chart_spec(loader(project_id, project_title=project_title), report_id)
