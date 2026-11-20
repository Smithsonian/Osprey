"""Worker update route: property=vlm_review (db/vlm_review.sql)."""

import json
from unittest.mock import MagicMock, patch

import pytest

KEY = '11111111-2222-3333-4444-555555556789'
ISSUES = [{'type': 'glare', 'severity': 'minor', 'description': 'hot spot, lower left'}]


@pytest.fixture()
def client():
    pytest.importorskip('flask_wtf')
    from app import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app.test_client()


def _post(client, data, transcription=0):
    from api.routes import worker
    rq = MagicMock(return_value=[{'project_id': 101, 'transcription': transcription}])
    ins = MagicMock(return_value=True)
    form = {'api_key': KEY, 'type': 'file', 'property': 'vlm_review',
            'file_id': '554388', 'folder_id': '9876', 'value': 'review',
            'issues': json.dumps(ISSUES), 'model': 'qwen3-vl:8b'}
    form.update(data)
    form = {k: v for k, v in form.items() if v is not None}
    with patch.object(worker, 'validate_api_key', return_value=(True, True)), \
            patch.object(worker, 'run_query', rq), \
            patch.object(worker, 'query_database_insert', ins):
        resp = client.post('/api/update/ento', data=form)
    return resp, ins


def test_stores_review_in_files_vlm_review(client):
    resp, ins = _post(client, {})
    assert resp.status_code == 200 and resp.get_json() == {'result': True}
    ins.assert_called_once()
    query, params = ins.call_args[0][:2]
    assert query.startswith('INSERT INTO files_vlm_review ')
    assert 'files_checks' not in query
    assert params == {'file_id': '554388', 'folder_id': '9876', 'verdict': 'review',
                      'issues': json.dumps(ISSUES, ensure_ascii=False), 'model': 'qwen3-vl:8b'}


def test_rerun_keeps_assessment_only_for_same_result(client):
    _, ins = _post(client, {})
    query = ins.call_args[0][0]
    update = query.split('ON DUPLICATE KEY UPDATE', 1)[1]
    # Staff columns are reset (when the result changed) before the result is overwritten.
    assert update.index('staff_assessment = IF(') < update.index('verdict = %(verdict)s')
    for col in ('assessed_by', 'assessed_at', 'staff_notes'):
        assert f'{col} = IF(' in update
    assert 'model <=> %(model)s' in update


def test_transcription_project_uses_transcription_table(client):
    resp, ins = _post(client, {'file_id': 'abc-uuid'}, transcription=1)
    assert resp.status_code == 200
    query, params = ins.call_args[0][:2]
    assert query.startswith('INSERT INTO transcription_files_vlm_review ')
    assert '(file_transcription_id, verdict, issues, model)' in query
    assert params['file_id'] == 'abc-uuid'


def test_unicode_issue_text_is_kept(client):
    issues = [{'type': 'other', 'severity': 'minor', 'description': 'étiquette illisible'}]
    _, ins = _post(client, {'issues': json.dumps(issues)})
    assert 'étiquette illisible' in ins.call_args[0][1]['issues']


@pytest.mark.parametrize('data, message', [
    ({'value': 'failed'}, 'value must be one of'),
    ({'issues': None}, 'issues is required'),
    ({'issues': 'not json'}, 'issues must be a JSON list'),
    ({'issues': '{"type": "glare"}'}, 'issues must be a JSON list'),
    ({'model': ''}, 'model is required'),
    ({'model': 'm' * 65}, 'at most 64'),
    ({'file_id': None}, 'file_id is required'),
])
def test_rejects_invalid_payloads(client, data, message):
    resp, ins = _post(client, data)
    assert resp.status_code == 400
    assert message in resp.get_json()['error']
    ins.assert_not_called()


def test_ok_with_no_issues(client):
    resp, ins = _post(client, {'value': 'ok', 'issues': '[]'})
    assert resp.status_code == 200
    assert ins.call_args[0][1]['issues'] == '[]'
