"""Program trends: monthly series, growth and unit charts, timeline, sparklines, and page access."""

from datetime import date
from unittest.mock import patch

import pytest

from osprey.services import program_trends as pt


# ---- monthly series --------------------------------------------------------

def test_pick_interval_prefers_the_finest_recognised_one():
    assert pt.pick_interval(['Yearly', 'monthly', 'weekly']) == 'weekly'
    assert pt.pick_interval(['month']) == 'month'
    assert pt.pick_interval(['Daily', 'monthly']) == 'Daily'
    assert pt.pick_interval([None, 'fiscal']) is None
    assert pt.pick_interval([]) is None


def test_series_uses_stats_detail_when_it_has_rows():
    def rq(query, params=None):
        if 'DISTINCT time_interval' in query:
            return [{'time_interval': 'monthly'}]
        assert 'projects_stats_detail' in query and params == {'interval': 'monthly'}
        return [{'project_id': 1, 'y': 2024, 'm': 3, 'images': 5, 'objects': 2}]

    with patch.object(pt, 'run_query', side_effect=rq):
        series = pt.load_monthly_series()
    assert series == {'source': pt.SOURCE_STATS,
                      'rows': [{'project_id': 1, 'month': '2024-03', 'images': 5, 'objects': 2}]}


def test_series_falls_back_to_file_capture_dates():
    def rq(query, params=None):
        if 'projects_stats_detail' in query:
            return []
        assert 'FROM files f' in query
        return [{'project_id': 1, 'y': 2024, 'm': 3, 'images': 5}]

    with patch.object(pt, 'run_query', side_effect=rq):
        series = pt.load_monthly_series()
    assert series['source'] == pt.SOURCE_FILES
    assert series['rows'] == [{'project_id': 1, 'month': '2024-03', 'images': 5, 'objects': None}]


_SERIES = {'source': pt.SOURCE_STATS, 'rows': [
    {'project_id': 1, 'month': '2024-01', 'images': 10, 'objects': 5},
    {'project_id': 2, 'month': '2024-01', 'images': 1, 'objects': 1},
    {'project_id': 1, 'month': '2024-03', 'images': 4, 'objects': 2},
]}


def test_growth_is_cumulative_across_projects():
    spec = pt.build_growth_chart_spec(_SERIES)
    images, objects = spec['datasets']
    assert images['data'] == [{'x': '2024-01-01', 'y': 11}, {'x': '2024-03-01', 'y': 15}]
    assert objects['data'][-1] == {'x': '2024-03-01', 'y': 8}
    assert spec['x_scale'] == 'time'
    assert spec['table_rows'][1] == {'month': '2024-03', 'images': 4, 'images_total': 15,
                                     'objects': 2, 'objects_total': 8}


def test_growth_from_files_has_no_object_line_and_says_so():
    series = {'source': pt.SOURCE_FILES, 'rows': [
        {'project_id': 1, 'month': '2024-01', 'images': 10, 'objects': None}]}
    spec = pt.build_growth_chart_spec(series)
    assert [d['label'] for d in spec['datasets']] == ['Images captured']
    assert 'not tracked here' in spec['note']
    assert pt.build_growth_chart_spec({'source': pt.SOURCE_FILES, 'rows': []})['empty']


# ---- units -----------------------------------------------------------------

def test_units_chart_is_horizontal_and_sized_by_rows():
    rows = [{'unit': 'NMNH', 'unit_fullname': 'Natural History', 'projects': 3, 'objects': 100, 'images': 250},
            {'unit': None, 'unit_fullname': None, 'projects': 1, 'objects': 0, 'images': 0}]
    spec = pt.build_units_chart_spec(rows)
    assert spec['index_axis'] == 'y'
    assert spec['labels'] == ['NMNH', 'Unknown']
    assert spec['datasets'][0]['data'] == [100, 0]
    assert spec['height_px'] >= 160
    assert pt.build_units_chart_spec([])['empty']


# ---- timeline --------------------------------------------------------------

_TODAY = date(2024, 7, 1)
_PROJECTS = [
    {'project_title': 'Done', 'project_alias': 'done', 'project_unit': 'NMNH', 'unit_fullname': 'Natural History',
     'project_status': 'Completed', 'project_manager': 'Ana', 'project_start': date(2022, 1, 1),
     'project_end': date(2022, 12, 31), 'objects_digitized': 10, 'collex_to_digitize': 10},
    {'project_title': 'Late', 'project_alias': 'late', 'project_unit': 'NMNH', 'unit_fullname': 'Natural History',
     'project_status': 'Ongoing', 'project_manager': None, 'project_start': date(2023, 1, 1),
     'project_end': date(2024, 1, 1), 'objects_digitized': 30, 'collex_to_digitize': 120},
    {'project_title': 'Running', 'project_alias': None, 'project_unit': 'NASM', 'unit_fullname': 'Air and Space',
     'project_status': 'Ongoing', 'project_manager': 'Ana', 'project_start': date(2024, 1, 1),
     'project_end': None, 'objects_digitized': 500, 'collex_to_digitize': 0},
    {'project_title': 'No start', 'project_status': 'Ongoing', 'project_start': None},
]


def test_timeline_positions_groups_and_late_flag():
    tl = pt.build_timeline(_PROJECTS, _TODAY)
    assert (tl['start'], tl['end']) == ('2022-01-01', '2024-12-31')
    assert [g['label'] for g in tl['groups']] == ['NASM', 'NMNH']
    assert (tl['total'], tl['ongoing'], tl['late']) == (3, 2, 1)
    done, late = tl['groups'][1]['rows']
    assert done['left'] == 0 and 33 < done['width'] < 34
    assert late['late'] and late['dates'] == '2023-01-01 to present'
    assert late['progress'] == 25
    running = tl['groups'][0]['rows'][0]
    assert running['progress'] is None and not running['late']
    # An ongoing project is drawn to today, not to the end of the axis.
    assert running['left'] + running['width'] < 90
    assert [y['label'] for y in tl['years']] == ['2022', '2023', '2024']


def test_timeline_can_group_by_manager_and_handles_no_projects():
    tl = pt.build_timeline(_PROJECTS, _TODAY, group_by='pm')
    assert [g['label'] for g in tl['groups']] == ['Ana', 'Unassigned']
    assert pt.build_timeline([], _TODAY)['empty']


# ---- sparklines ------------------------------------------------------------

def test_last_months_crosses_the_year_boundary():
    months = pt.last_months(date(2024, 2, 15))
    assert len(months) == 12 and months[0] == '2023-03' and months[-1] == '2024-02'


def test_recent_activity_keeps_only_the_last_year():
    series = {'rows': [
        {'project_id': 1, 'month': '2024-02', 'images': 7, 'objects': 0},
        {'project_id': 1, 'month': '2020-02', 'images': 99, 'objects': 0},
        {'project_id': 2, 'month': '2019-01', 'images': 5, 'objects': 0},
    ]}
    activity = pt.recent_activity(series, date(2024, 2, 15))
    assert list(activity) == [1]
    assert activity[1][-1] == 7 and sum(activity[1]) == 7


def test_sparkline_svg_has_a_text_alternative_and_escapes():
    months = pt.last_months(date(2024, 2, 15))
    svg = pt.sparkline_svg([0] * 10 + [5, 10], months)
    assert svg.startswith('<svg') and svg.count('<rect') == 12
    assert 'role="img"' in svg and 'most in 2024-02 (10)' in svg
    assert pt.sparkline_svg(None, months) == ''
    assert pt.sparkline_svg([0] * 12, months) == ''


# ---- pages -----------------------------------------------------------------

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')
pytest.importorskip('pandas')

from app import app  # noqa: E402
from cache import cache  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    app.config['TESTING'] = True
    monkeypatch.setattr(app, 'secret_key', 'test-only-not-a-secret')
    cache.clear()
    yield app.test_client()
    cache.clear()


def test_trends_page_is_public_and_draws_all_three(client):
    with patch.object(pt, 'load_monthly_series', return_value=_SERIES), \
            patch.object(pt, 'load_unit_rows', return_value=[
                {'unit': 'NMNH', 'unit_fullname': 'Natural History', 'projects': 2, 'objects': 9, 'images': 20}]), \
            patch.object(pt, 'load_timeline_rows', return_value=_PROJECTS):
        response = client.get('/trends/')
        csv = client.get('/trends/growth.csv')
        missing = client.get('/trends/nope.csv')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="chart-growth"' in html and 'id="chart-units"' in html
    assert 'osprey-timeline-bar' in html and '/dashboard/late' in html
    # Progress and the late flag belong to the logged-in portfolio only.
    assert 'Past planned end' not in html
    assert csv.status_code == 200 and csv.get_data(as_text=True).splitlines()[0].startswith('Month,Images')
    assert missing.status_code == 404


def test_portfolio_requires_login(client):
    response = client.get('/portfolio/')
    assert response.status_code in (301, 302, 401)


@pytest.mark.parametrize('report_id', ['qc_outcomes', 'reviewer_workload'])
@pytest.mark.parametrize('suffix', ['', 'download.csv'])
def test_members_only_reports_are_404_for_anonymous_visitors(client, report_id, suffix):
    from osprey.services import builtin_reports as br
    with patch('web.reports.report_service.get_project_id', return_value=7), \
            patch('web.reports.report_service.get_project_report', side_effect=br.get_builtin_report), \
            patch('web.reports.builtin_report_service.load_chart_report') as load:
        response = client.get(f'/reports/demo/{report_id}/{suffix}')
    assert response.status_code == 404
    load.assert_not_called()


def test_members_only_report_is_served_to_project_members(client):
    from osprey.services import builtin_reports as br
    from osprey.services.reviewer_workload import build_reviewer_workload_chart_spec
    chart = br.finish_chart_spec(build_reviewer_workload_chart_spec([], pending=3), 'reviewer_workload')
    with patch('web.reports.report_service.get_project_id', return_value=7), \
            patch('web.reports.report_service.get_project_report',
                  return_value=br.get_builtin_report(7, 'reviewer_workload')), \
            patch('web.reports.report_service.get_project', return_value={'project_title': 'Demo'}), \
            patch('web.reports.project_member', return_value=True), \
            patch('web.reports.builtin_report_service.load_chart_report', return_value=chart):
        response = client.get('/reports/demo/reviewer_workload/')
    assert response.status_code == 200
    assert 'Folders waiting for QC' in response.get_data(as_text=True)


def test_member_listing_filter():
    from osprey.services import reports as rs
    rows = [{'report_id': 'a'}, {'report_id': 'qc_outcomes', 'members_only': True}]
    with patch.object(rs.builtin_reports, 'list_project_reports', return_value=rows):
        assert [r['report_id'] for r in rs.list_project_reports(7)] == ['a']
        assert rs.list_project_reports(7, include_members_only=True) == rows
