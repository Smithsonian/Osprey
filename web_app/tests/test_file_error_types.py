"""Unit tests for the file error types chart helpers."""

from osprey.services.builtin_reports import chart_spec_for_js
from osprey.services.file_error_types import build_file_error_type_chart_spec


def test_build_file_error_type_chart_spec_labels_and_counts():
    rows = [
        {'file_check': 'file_name', 'error_count': 5},
        {'file_check': 'tif_compression', 'error_count': 2},
        {'file_check': 'made_up_check', 'error_count': 1},
    ]
    spec = build_file_error_type_chart_spec(rows, project_title='Demo')
    assert spec['empty'] is False
    assert spec['labels'] == ['File name', 'TIF compression', 'Made Up Check']
    assert spec['datasets'][0]['data'] == [5, 2, 1]
    assert spec['table_rows'] == [
        {'check': 'File name', 'count': 5},
        {'check': 'TIF compression', 'count': 2},
        {'check': 'Made Up Check', 'count': 1},
    ]
    assert spec['table_columns'] == [
        {'key': 'check', 'label': 'Error type'},
        {'key': 'count', 'label': 'Files'},
    ]


def test_build_file_error_type_chart_spec_empty():
    spec = build_file_error_type_chart_spec([], project_title='Demo')
    assert spec['empty'] is True
    assert spec['labels'] == []
    assert spec['datasets'][0]['data'] == []


def test_chart_spec_for_js_omits_time_fields_for_error_types():
    js_spec = chart_spec_for_js({
        'step_id': 'file_error_types',
        'chart_js_type': 'bar',
        'labels': ['File name'],
        'datasets': [{'label': 'Files with errors', 'data': [5]}],
    })
    assert 'x_scale' not in js_spec
    assert js_spec['step_id'] == 'file_error_types'
    assert js_spec['labels'] == ['File name']
