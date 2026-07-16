"""Unit tests for daily throughput chart helpers."""

import sys
import types
from datetime import date, datetime
from unittest.mock import MagicMock

if 'osprey.db' not in sys.modules:
    _db = types.ModuleType('osprey.db')
    _db.run_query = MagicMock(return_value=[])
    _db.query_database_insert = MagicMock()
    sys.modules['osprey.db'] = _db

from osprey.services.builtin_reports import chart_spec_for_js  # noqa: E402
from osprey.services.daily_throughput import (  # noqa: E402
    _format_day,
    build_daily_throughput_chart_spec,
)


def test_format_day_accepts_date_and_datetime():
    assert _format_day(date(2024, 1, 15)) == '2024-01-15'
    assert _format_day(datetime(2024, 1, 15, 12, 30)) == '2024-01-15'
    assert _format_day('2024-01-15 00:00:00') == '2024-01-15'


def test_build_daily_throughput_chart_spec_uses_time_scale():
    rows = [
        {'day': date(2024, 1, 1), 'images': 2, 'objects': 1},
        {'day': date(2024, 1, 3), 'images': 4, 'objects': 2},
    ]
    spec = build_daily_throughput_chart_spec(rows, project_title='Demo')
    assert spec['x_scale'] == 'time'
    assert spec['time_unit'] == 'day'
    assert spec['labels'] == ['2024-01-01', '2024-01-03']
    assert spec['datasets'][0]['data'] == [
        {'x': '2024-01-01', 'y': 2},
        {'x': '2024-01-03', 'y': 4},
    ]
    assert spec['datasets'][1]['data'] == [
        {'x': '2024-01-01', 'y': 1},
        {'x': '2024-01-03', 'y': 2},
    ]


def test_chart_spec_for_js_omits_missing_time_fields():
    js_spec = chart_spec_for_js({
        'step_id': 'daily_throughput',
        'chart_js_type': 'bar',
        'labels': ['2024-01-01'],
        'datasets': [],
    })
    assert 'x_scale' not in js_spec
    assert js_spec['step_id'] == 'daily_throughput'


def test_chart_spec_for_js_includes_time_fields():
    js_spec = chart_spec_for_js({
        'step_id': 'daily_throughput',
        'x_scale': 'time',
        'time_unit': 'day',
        'labels': [],
        'datasets': [],
    })
    assert js_spec['x_scale'] == 'time'
    assert js_spec['time_unit'] == 'day'
