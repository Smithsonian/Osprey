"""Unit tests for project statistics chart helpers."""

import sys
import types
from unittest.mock import MagicMock, patch

# Stub DB before importing services (test env may lack mysql.connector).
if 'osprey.db' not in sys.modules:
    _db = types.ModuleType('osprey.db')
    _db.run_query = MagicMock(return_value=[])
    _db.query_database_insert = MagicMock()
    sys.modules['osprey.db'] = _db

from osprey.services.project_statistics import (  # noqa: E402
    build_chart_spec,
    describe_chart,
    normalize_chart_rows,
)


def test_normalize_chart_rows_drops_invalid():
    rows = [
        {'date': '2024-01-01', 'step_value': '10', 'file_name': None},
        {'date': '2024-01-02', 'step_value': 'bad', 'file_name': None},
        {'date': '2024-01-03', 'step_value': '', 'file_name': None},
        {'date': '2024-01-04', 'step_value': '3.14159', 'file_name': 'a.tif'},
    ]
    out = normalize_chart_rows(rows, round_val=2)
    assert len(out) == 2
    assert out[0]['value'] == 10.0
    assert out[1]['value'] == 3.14
    assert out[1]['file_name'] == 'a.tif'


def test_describe_chart_empty():
    step = {'step_info': 'Daily files', 'step_notes': 'Notes here', 'step_units': 'files'}
    short, long_desc = describe_chart(step, [], [], [], chart_kind='bar')
    assert 'No data available' in short
    assert 'Daily files' in short
    assert 'Notes here' in long_desc


def test_describe_chart_with_values():
    step = {'step_info': 'Daily files', 'step_notes': '', 'step_units': 'files'}
    labels = ['2024-01-01', '2024-01-02', '2024-01-03']
    values = [1.0, 3.0, 5.0]
    short, long_desc = describe_chart(step, [], labels, values, chart_kind='bar')
    assert 'Bar chart' in short
    assert '3 points' in short
    assert 'increasing' in long_desc
    assert 'files' in long_desc


def test_build_chart_spec_column():
    step = {
        'step_id': 'abc',
        'step_info': 'Files per day',
        'step_notes': 'Ingested files',
        'step_units': 'files',
        'stat_type': 'column',
        'round_val': 0,
        'step_updated_on_fmt': '2024-06-01 12:00:00',
    }
    rows = [
        {'date': '2024-01-01', 'step_value': '2', 'file_name': None},
        {'date': '2024-01-01', 'step_value': '3', 'file_name': None},
        {'date': '2024-01-02', 'step_value': '4', 'file_name': None},
    ]
    fig = build_chart_spec(step, rows, project_title='Demo Project')
    assert fig['empty'] is False
    assert fig['chart_js_type'] == 'bar'
    assert fig['labels'] == ['2024-01-01', '2024-01-02']
    assert fig['datasets'][0]['data'] == [5.0, 4.0]
    assert 'Demo Project' in fig['short_description']
    assert fig['table_mode'] == 'series'
    assert len(fig['table_rows']) == 3


def test_build_chart_spec_area():
    step = {
        'step_id': 'area1',
        'step_info': 'Cumulative',
        'step_notes': '',
        'step_units': '',
        'stat_type': 'area',
        'round_val': 1,
        'step_updated_on_fmt': '2024-06-01 12:00:00',
    }
    rows = [
        {'date': '2024-02-01', 'step_value': '1.5', 'file_name': None},
        {'date': '2024-02-02', 'step_value': '2.5', 'file_name': None},
    ]
    fig = build_chart_spec(step, rows)
    assert fig['chart_js_type'] == 'line'
    assert fig['datasets'][0]['fill'] is True


def test_build_chart_spec_boxplot():
    step = {
        'step_id': 'box1',
        'step_info': 'Quality scores',
        'step_notes': 'By folder',
        'step_units': 'score',
        'stat_type': 'boxplot',
        'round_val': 1,
        'step_updated_on_fmt': '2024-06-01 12:00:00',
    }
    rows = [
        {'date': '2024-01-01', 'step_value': '1', 'file_name': 'folderA'},
        {'date': '2024-01-01', 'step_value': '3', 'file_name': 'folderA'},
        {'date': '2024-01-01', 'step_value': '5', 'file_name': 'folderA'},
        {'date': '2024-01-02', 'step_value': '2', 'file_name': 'folderB'},
        {'date': '2024-01-02', 'step_value': '4', 'file_name': 'folderB'},
        {'date': '2024-01-02', 'step_value': '6', 'file_name': 'folderB'},
    ]
    fig = build_chart_spec(step, rows)
    assert fig['chart_type'] == 'boxplot'
    assert fig['chart_js_type'] == 'bar'
    assert fig['table_mode'] == 'boxplot'
    assert set(fig['labels']) == {'folderA', 'folderB'}
    assert 'Distribution summaries' in fig['long_description']
    assert fig['table_rows'][0]['median'] is not None


def test_build_chart_spec_empty():
    step = {
        'step_id': 'empty1',
        'step_info': 'Empty series',
        'step_notes': '',
        'step_units': '',
        'stat_type': 'column',
        'round_val': 2,
        'step_updated_on_fmt': '2024-06-01 12:00:00',
    }
    fig = build_chart_spec(step, [])
    assert fig['empty'] is True
    assert fig['labels'] == []
    assert 'No data available' in fig['short_description']


@patch('osprey.services.project_statistics.run_query')
def test_load_statistics_page_context_not_found(mock_run_query):
    from osprey.services.project_statistics import load_statistics_page_context

    mock_run_query.return_value = []
    ctx = load_statistics_page_context('missing-project')
    assert ctx['found'] is False
