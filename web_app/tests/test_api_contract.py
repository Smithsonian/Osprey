"""Contract tests for API response shapes."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / 'api_responses'


def _load_fixture(name):
    with open(FIXTURES / name, encoding='utf-8') as handle:
        return json.load(handle)


def test_folder_fixture_top_level_keys():
    data = _load_fixture('folder.json')
    for key in (
        'delivered_to_dams', 'error_info', 'file_errors', 'files',
        'folder', 'folder_date', 'folder_id', 'previews', 'project_alias',
        'project_id', 'qc_status', 'status',
    ):
        assert key in data


def test_folder_fixture_file_row_keys():
    data = _load_fixture('folder.json')
    assert len(data['files']) > 0
    sample = data['files'][0]
    for key in ('file_id', 'file_name', 'file_timestamp', 'created_at', 'updated_at'):
        assert key in sample


def test_folder_files_fixture_file_checks_shape():
    """files[].file_checks is an array of check objects (see /api/folders/<id>/files)."""
    data = _load_fixture('folder.json')
    if not data.get('files'):
        pytest.skip('folder.json has no files')
    sample = data['files'][0]
    if 'file_checks' not in sample:
        pytest.skip('legacy flat-column fixture')
    assert isinstance(sample['file_checks'], list)
    if sample['file_checks']:
        check = sample['file_checks'][0]
        for key in ('file_check', 'check_results', 'check_info', 'updated_at'):
            assert key in check
        assert check['check_results'] in ('OK', 'Pending', 'Failed')

    data = _load_fixture('project_folders.json')
    assert 'folders' in data
    rows = data['folders']
    assert len(rows) > 0
    row = rows[0]
    for key in ('folder_id', 'project_id', 'folder', 'status', 'capture_date'):
        assert key in row


def test_api_blueprint_route_prefixes():
    """Blueprint routes are mounted under /api when the app loads."""
    pytest.importorskip('flask')
    from app import app

    api_rules = sorted(rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith('/api'))
    assert '/api/' in api_rules
    assert '/api/projects/' in api_rules
    assert '/api/folders/<folder_id>/files' in api_rules
    assert '/api/folders/<folder_id>' in api_rules
    assert '/api/files/<int:file_id>' in api_rules


def test_site_net_api_redirect_target():
    pytest.importorskip('flask')
    from app import app

    with app.test_request_context():
        from flask import url_for
        assert url_for('api.api_route_list') == '/api/'
