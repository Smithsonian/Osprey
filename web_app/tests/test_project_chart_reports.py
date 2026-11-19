"""Unit tests for the per-project chart reports added alongside daily throughput:
folder pipeline, error rate by delivery, QC outcomes, turnaround times, capture
calendar, storage growth, reviewer workload and the transcription grid."""

from datetime import date, datetime

from osprey.services import builtin_reports
from osprey.services.capture_calendar import build_capture_calendar_spec
from osprey.services.chart_helpers import five_numbers, heat_level, percent
from osprey.services.folder_error_rates import build_folder_error_rate_chart_spec
from osprey.services.folder_pipeline import build_folder_pipeline_chart_spec, folder_stage
from osprey.services.qc_outcomes import build_qc_outcomes_chart_spec
from osprey.services.reviewer_workload import build_reviewer_workload_chart_spec
from osprey.services.storage_growth import build_storage_growth_chart_spec
from osprey.services.transcription_grid import build_transcription_grid_spec
from osprey.services.turnaround_times import build_turnaround_chart_spec


# ---- helpers ---------------------------------------------------------------

def test_percent_and_heat_level_handle_empty_denominators():
    assert percent(1, 0) == 0
    assert percent(1, 4) == 25.0
    assert heat_level(0, 10) == 0
    assert heat_level(1, 10) == 1
    assert heat_level(10, 10) == 4


def test_five_numbers():
    assert five_numbers([]) is None
    assert five_numbers([3]) == {'n': 1, 'min': 3, 'q1': 3, 'median': 3, 'q3': 3, 'max': 3}
    stats = five_numbers([1, 2, 3, 4, 5])
    assert (stats['min'], stats['q1'], stats['median'], stats['q3'], stats['max']) == (1, 2, 3, 4, 5)


# ---- folder pipeline -------------------------------------------------------

def test_folder_stage_takes_the_furthest_stage_reached():
    assert folder_stage({'status': 9}) == 'checking'
    assert folder_stage({'status': 1, 'delivered_to_dams': 9}) == 'errors'
    assert folder_stage({'status': 0, 'file_errors': 1}) == 'errors'
    assert folder_stage({'status': 0, 'delivered_to_dams': 9, 'qc_status': 9}) == 'awaiting_qc'
    assert folder_stage({'status': 0, 'qc_status': 1}) == 'qc_failed'
    assert folder_stage({'status': 0, 'qc_status': 0, 'delivered_to_dams': 9}) == 'qc_passed'
    assert folder_stage({'status': 0, 'qc_status': 0, 'delivered_to_dams': 1}) == 'ready_dams'
    assert folder_stage({'status': 0, 'qc_status': 0, 'delivered_to_dams': 0}) == 'in_dams'


def test_folder_pipeline_counts_and_waits():
    rows = [
        {'project_folder': 'a', 'status': 0, 'qc_status': None, 'no_files': 10, 'days_since_change': 3},
        {'project_folder': 'b', 'status': 0, 'qc_status': 9, 'no_files': 20, 'days_since_change': 9},
        {'project_folder': 'c', 'status': 0, 'qc_status': 0, 'delivered_to_dams': 0, 'no_files': 5,
         'days_since_change': 400},
    ]
    spec = build_folder_pipeline_chart_spec(rows, project_title='Demo')
    by_stage = {row['stage']: row for row in spec['table_rows']}
    waiting = by_stage['Waiting for QC']
    assert (waiting['folders'], waiting['files']) == (2, 30)
    assert (waiting['median_days'], waiting['max_days'], waiting['oldest_folder']) == (6, 9, 'b')
    # Finished folders are counted but have no waiting time.
    assert by_stage['In DAMS']['folders'] == 1
    assert by_stage['In DAMS']['max_days'] == ''
    assert spec['datasets'][0]['data'] == [0, 0, 2, 0, 0, 0, 1]
    assert not spec['empty']
    assert build_folder_pipeline_chart_spec([])['empty']


# ---- error rate by delivery ------------------------------------------------

def test_folder_error_rates_stack_checks_per_folder():
    rows = [
        {'folder_id': 1, 'project_folder': 'f1', 'folder_date': date(2024, 1, 1), 'no_files': 100,
         'no_files_errors': 4, 'file_check': 'jhove', 'error_count': 4},
        {'folder_id': 1, 'project_folder': 'f1', 'folder_date': date(2024, 1, 1), 'no_files': 100,
         'no_files_errors': 4, 'file_check': 'magick', 'error_count': 1},
        {'folder_id': 2, 'project_folder': 'f2', 'folder_date': date(2024, 1, 2), 'no_files': 50,
         'no_files_errors': 0, 'file_check': None, 'error_count': 0},
    ]
    spec = build_folder_error_rate_chart_spec(rows)
    assert spec['stacked'] is True
    assert spec['labels'] == ['f1', 'f2']
    assert [d['label'] for d in spec['datasets']] == ['JHOVE', 'ImageMagick']
    assert spec['datasets'][0]['data'] == [4.0, 0]
    assert spec['table_rows'][0]['pct_with_errors'] == 4.0
    assert spec['table_rows'][1]['check_jhove'] == 0
    assert [c['key'] for c in spec['table_columns']][-2:] == ['check_jhove', 'check_magick']


def test_folder_error_rates_without_any_failure_still_draws():
    rows = [{'folder_id': 1, 'project_folder': 'f1', 'folder_date': None, 'no_files': 0,
             'no_files_errors': 0, 'file_check': None, 'error_count': 0}]
    spec = build_folder_error_rate_chart_spec(rows)
    assert not spec['empty']
    assert spec['datasets'][0]['data'] == [0]


# ---- QC outcomes -----------------------------------------------------------

_QC_ROWS = [
    {'folder_id': 1, 'project_folder': 'f1', 'qc_status': 0, 'qc_level': 'Normal', 'qc_method': 'weighted',
     'qc_date': datetime(2024, 1, 5, 10), 'sampled': 100, 'critical': 0, 'major': 2, 'minor': 10},
    {'folder_id': 2, 'project_folder': 'f2', 'qc_status': 1, 'qc_level': 'Tightened', 'qc_method': 'weighted',
     'qc_date': datetime(2024, 1, 9, 10), 'sampled': 50, 'critical': 1, 'major': 0, 'minor': 0},
]
_SETTINGS = {'qc_method': 'weighted', 'w_major': '1', 'w_minor': '0.3', 'weighted_rate': '6',
             'qc_threshold_critical': '0', 'qc_threshold_major': '1.5', 'qc_threshold_minor': '4'}


def test_qc_outcomes_weighted_stack_is_comparable_to_the_weighted_limit():
    spec = build_qc_outcomes_chart_spec(_QC_ROWS, _SETTINGS)
    labels = [d['label'] for d in spec['datasets']]
    assert labels == ['Major (weighted)', 'Minor (weighted)', 'Weighted rate limit']
    assert spec['datasets'][0]['data'] == [2.0, 0]
    assert spec['datasets'][1]['data'] == [3.0, 0]      # 10 minor x 0.3 of 100
    limit = spec['datasets'][2]
    assert limit['data'] == [6.0, 6.0] and limit['type'] == 'line' and limit['stack'] == 'limit'
    assert spec['table_rows'][1]['result'] == 'Failed'
    assert spec['table_rows'][1]['level'] == 'Tightened'
    assert spec['table_rows'][1]['critical'] == 1


def test_qc_outcomes_cumulative_stacks_all_issues_against_the_minor_limit():
    settings = dict(_SETTINGS, qc_method='cumulative')
    spec = build_qc_outcomes_chart_spec(_QC_ROWS, settings)
    assert [d['label'] for d in spec['datasets']] == ['Critical', 'Major', 'Minor', 'Limit for all issues']
    assert spec['datasets'][0]['data'] == [0, 2.0]
    assert spec['datasets'][2]['data'] == [10.0, 0]
    assert spec['datasets'][3]['data'] == [4.0, 4.0]


def test_qc_outcomes_without_settings_or_rows():
    assert build_qc_outcomes_chart_spec([], None)['empty']
    spec = build_qc_outcomes_chart_spec(_QC_ROWS, None)
    assert [d['label'] for d in spec['datasets']] == ['Critical', 'Major', 'Minor']


# ---- turnaround times ------------------------------------------------------

def test_turnaround_medians_and_missing_or_negative_gaps():
    milestones = {
        1: {'captured': datetime(2024, 1, 1), 'delivered': datetime(2024, 1, 3),
            'qc_decided': datetime(2024, 1, 7), 'in_dams': datetime(2024, 1, 8)},
        2: {'captured': datetime(2024, 1, 1), 'delivered': datetime(2024, 1, 5),
            'qc_decided': None},
        # Captured "after" delivery: a clock problem, not a turnaround.
        3: {'captured': datetime(2024, 2, 1), 'delivered': datetime(2024, 1, 5)},
    }
    spec = build_turnaround_chart_spec(milestones)
    capture, qc, dams = spec['table_rows']
    assert (capture['n'], capture['median']) == (2, 3.0)
    assert (qc['n'], qc['median']) == (1, 4.0)
    assert (dams['n'], dams['median']) == (1, 1.0)
    assert spec['datasets'][0]['data'] == [3.0, 4.0, 1.0]
    assert build_turnaround_chart_spec({})['empty']


# ---- capture calendar ------------------------------------------------------

def test_capture_calendar_lays_days_out_by_week():
    rows = [
        {'day': date(2024, 1, 2), 'images': 10},     # Tuesday
        {'day': date(2024, 1, 10), 'images': 40},    # Wednesday of the next week
    ]
    spec = build_capture_calendar_spec(rows, {'2024-01-01'})
    grid = spec['grids'][0]
    assert grid['columns'][0] == 'Mon' and len(grid['rows']) == 2
    first, second = grid['rows']
    assert first['label'] == '2024-01-01'
    assert first['cells'][0]['text'] == 'H'            # holiday, nothing captured
    assert first['cells'][1]['text'] == '10' and first['cells'][1]['level'] == 1
    assert second['cells'][2]['text'] == '40' and second['cells'][2]['level'] == 4
    assert spec['table_rows'][0] == {'date': '2024-01-02', 'weekday': 'Tue', 'images': 10, 'holiday': ''}
    assert not spec['datasets']


def test_capture_calendar_shows_at_most_a_year_but_exports_everything():
    rows = [{'day': date(2020, 1, 6), 'images': 1}, {'day': date(2024, 1, 8), 'images': 1}]
    spec = build_capture_calendar_spec(rows)
    assert len(spec['grids'][0]['rows']) == 52
    assert len(spec['table_rows']) == 2
    assert build_capture_calendar_spec([])['empty']


# ---- storage growth --------------------------------------------------------

def test_storage_growth_is_cumulative_per_file_type_over_folder_dates():
    gb = 1024 ** 3
    rows = [
        {'folder_id': 1, 'project_folder': 'f1', 'folder_date': date(2024, 1, 1), 'filetype': 'TIF',
         'files': 2, 'bytes': 2 * gb},
        {'folder_id': 2, 'project_folder': 'f2', 'folder_date': date(2024, 1, 2), 'filetype': 'RAW',
         'files': 1, 'bytes': gb},
        {'folder_id': 2, 'project_folder': 'f2', 'folder_date': date(2024, 1, 2), 'filetype': 'TIF',
         'files': 1, 'bytes': 3 * gb},
        # Same date as f2: added into the same point.
        {'folder_id': 3, 'project_folder': 'f3', 'folder_date': datetime(2024, 1, 2, 9), 'filetype': 'TIF',
         'files': 1, 'bytes': gb},
    ]
    spec = build_storage_growth_chart_spec(rows)
    assert spec['x_scale'] == 'time' and spec['time_unit'] == 'day'
    assert spec['labels'] == ['2024-01-01', '2024-01-02']
    series = {d['label']: d['data'] for d in spec['datasets']}
    assert series == {
        'RAW': [{'x': '2024-01-01', 'y': 0.0}, {'x': '2024-01-02', 'y': 1.0}],
        'TIF': [{'x': '2024-01-01', 'y': 2.0}, {'x': '2024-01-02', 'y': 6.0}],
    }
    assert spec['table_rows'][0]['avg_mb'] == 1024.0
    assert len(spec['table_rows']) == 4
    assert build_storage_growth_chart_spec([])['empty']


def test_storage_growth_leaves_undated_folders_off_the_chart():
    rows = [
        {'folder_id': 1, 'project_folder': 'f1', 'folder_date': None, 'filetype': 'TIF', 'files': 1, 'bytes': 5},
        {'folder_id': 2, 'project_folder': 'f2', 'folder_date': date(2024, 3, 1), 'filetype': 'TIF',
         'files': 1, 'bytes': 5},
    ]
    spec = build_storage_growth_chart_spec(rows)
    assert spec['labels'] == ['2024-03-01']
    assert '1 folder(s) have no date' in spec['note']
    assert [row['folder'] for row in spec['table_rows']] == ['f1', 'f2']
    only_undated = build_storage_growth_chart_spec(rows[:1])
    assert only_undated['empty'] and only_undated['table_rows']


def test_storage_growth_time_unit_follows_the_span():
    from osprey.services.storage_growth import pick_time_unit
    assert pick_time_unit('2024-01-01', '2024-03-01') == 'day'
    assert pick_time_unit('2024-01-01', '2025-06-01') == 'month'
    assert pick_time_unit('2018-01-01', '2025-06-01') == 'year'


# ---- reviewer workload -----------------------------------------------------

def test_reviewer_workload_fills_idle_weeks():
    rows = [
        {'week_start': date(2024, 1, 1), 'reviewer': 'Ana', 'folders': 3, 'files': 30},
        {'week_start': date(2024, 1, 15), 'reviewer': 'Ben', 'folders': 1, 'files': 12},
    ]
    spec = build_reviewer_workload_chart_spec(rows, pending=4)
    assert spec['labels'] == ['2024-01-01', '2024-01-08', '2024-01-15']
    series = {d['label']: d['data'] for d in spec['datasets']}
    assert series == {'Ana': [3, 0, 0], 'Ben': [0, 0, 1]}
    assert spec['summary'][0] == {'label': 'Folders waiting for QC', 'value': 4}
    assert spec['stacked'] is True


def test_reviewer_workload_with_only_a_queue_is_not_empty():
    assert not build_reviewer_workload_chart_spec([], pending=2)['empty']
    assert build_reviewer_workload_chart_spec([], pending=0)['empty']


# ---- transcription grid ----------------------------------------------------

def test_transcription_grid_cells_costs_and_qc():
    fill = [
        {'source_id': 's1', 'source_name': 'Vendor', 'folder_id': 'a', 'folder_name': 'batch1',
         'field_id': 'f1', 'field_name': 'Country', 'total_files': 10, 'filled': 10},
        {'source_id': 's1', 'source_name': 'Vendor', 'folder_id': 'a', 'folder_name': 'batch1',
         'field_id': 'f2', 'field_name': 'Collector', 'total_files': 10, 'filled': 2},
        {'source_id': 's1', 'source_name': 'Vendor', 'folder_id': 'b', 'folder_name': 'batch2',
         'field_id': 'f1', 'field_name': 'Country', 'total_files': 10, 'filled': 5},
    ]
    spec = build_transcription_grid_spec(
        fill, {'f1': 0.5}, {'s1': {'passed': 3, 'failed': 1, 'pending': 2}})
    grid = spec['grids'][0]
    assert grid['columns'] == ['Country', 'Collector']
    assert [cell['text'] for cell in grid['rows'][0]['cells']] == ['100%', '20%']
    # batch2 has no Collector row: blank, not 0%.
    assert grid['rows'][1]['cells'][1]['text'] == ''
    country = spec['table_rows'][0]
    assert (country['filled'], country['fill_pct'], country['total_cost']) == (15, 75.0, 7.5)
    assert spec['table_rows'][1]['cost_per_field'] == ''
    values = {item['label']: item['value'] for item in spec['summary']}
    assert values['QC pass rate: Vendor'] == '75% of 4 folder(s)'
    assert values['Cost of filled fields: Vendor'] == '7.50'
    assert build_transcription_grid_spec([])['empty']


# ---- registry --------------------------------------------------------------

def test_every_builtin_chart_report_has_a_loader():
    chart_ids = {rid for rid, meta in builtin_reports.BUILTIN_REPORT_DEFS.items() if meta['render'] == 'chart'}
    assert chart_ids == set(builtin_reports.CHART_LOADERS)


def test_members_only_reports_are_flagged():
    flagged = {rid for rid, meta in builtin_reports.BUILTIN_REPORT_DEFS.items()
               if builtin_reports.is_members_only(meta)}
    assert flagged == {'qc_outcomes', 'reviewer_workload'}


def test_chart_spec_for_js_passes_layout_switches():
    js_spec = builtin_reports.chart_spec_for_js({'stacked': True, 'index_axis': 'y'})
    assert js_spec['stacked'] is True and js_spec['index_axis'] == 'y'
    assert 'stacked' not in builtin_reports.chart_spec_for_js({})


# ---- dashboard report menus -----------------------------------------------

def test_group_reports_orders_categories_and_marks_kinds():
    reports = [
        {'report_id': 7, 'report_title': 'Specimen status', 'pregenerated': 1},
        {'report_id': 8, 'report_title': 'Live list', 'pregenerated': 0, 'sysadmin_only': 1},
    ] + [builtin_reports.get_builtin_report(1, rid)
         for rid in ('qc_outcomes', 'folder_pipeline', 'daily_throughput', 'transcription_profile')]
    groups = builtin_reports.group_reports(reports)
    assert [g['key'] for g in groups] == ['production', 'quality', 'workflow', 'project_data']
    by_key = {g['key']: g['reports'] for g in groups}
    assert [r['report_id'] for r in by_key['project_data']] == [7, 8, 'transcription_profile']
    export, live, nightly = by_key['project_data']
    assert (export['kind_label'], export['access_label']) == ('Export file', '')
    assert (live['kind_label'], live['access_label']) == ('Live table', 'Sysadmin only')
    assert nightly['kind_icon'] == 'fa-moon'
    qc = by_key['quality'][0]
    assert (qc['kind_label'], qc['access_label']) == ('Chart', 'Project team only')
    # The input rows are not changed.
    assert 'kind_label' not in reports[0]


def test_group_reports_leaves_out_empty_categories():
    assert builtin_reports.group_reports([]) == []
    only = builtin_reports.group_reports([builtin_reports.get_builtin_report(1, 'storage_growth')])
    assert [g['key'] for g in only] == ['production']


def test_every_builtin_report_has_a_known_category():
    known = {key for key, _, _ in builtin_reports.REPORT_CATEGORIES}
    assert all(meta.get('category') in known for meta in builtin_reports.BUILTIN_REPORT_DEFS.values())
