"""osprey.audit: audit rows, actor resolution, details, and call sites."""

import logging
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip('flask')
pytest.importorskip('flask_login')

from flask import Flask, g

from osprey import audit

KEY = '11111111-2222-3333-4444-555555556789'


@pytest.fixture()
def db(_isolate_audit_db):
    return _isolate_audit_db


def _row(db):
    query, params = db.query_database_insert.call_args[0][:2]
    assert query.startswith('INSERT INTO audit_log')
    return params


def test_script_context_row(db):
    db.run_query.return_value = [{'project_id': 7, 'project_alias': 'ento', 'folder_name': 'ENT-1'}]
    db.query_database_insert.return_value = 42
    assert audit.record('update', 'folder', 'qc_reset', folder_ref=9876) == 42
    row = _row(db)
    assert row['actor_type'] == 'system' and row['source'] == 'script'
    assert row['action'] == 'update' and row['entity'] == 'folder' and row['event'] == 'qc_reset'
    assert row['folder_ref'] == '9876' and row['file_ref'] is None
    # Names and project come from the context lookup.
    assert row['project_id'] == 7 and row['project_alias'] == 'ento' and row['folder_name'] == 'ENT-1'
    assert row['request_id'] is None
    assert 'FROM folders fo' in db.run_query.call_args[0][0]


def test_file_lookup_uses_transcription_tables(db):
    audit.record('insert', 'file', 'created', file_ref='abc-uuid', transcription=True)
    assert 'FROM transcription_files f' in db.run_query.call_args[0][0]
    assert _row(db)['transcription'] == 1


def test_api_actor_and_details(db):
    app = Flask(__name__)
    long_value = 'x' * 5000
    with app.test_request_context('/api/update/ento', method='POST',
                                  data={'api_key': KEY, 'property': 'exif', 'value': long_value}):
        g.api_actor = 'worker_01'
        with patch.object(audit.audit_logger, 'info') as log_info:
            audit.record('update', 'file', 'datetime_created', file_ref=5)
        rid = g.request_id
    row = _row(db)
    assert row['actor_type'] == 'api_key' and row['actor'] == 'worker_01' and row['source'] == 'api'
    assert row['request_id'] == rid and len(rid) == 32
    line = log_info.call_args[0][0]
    assert 'request_id={}'.format(rid) in line
    assert KEY not in line and '"api_key"' not in line  # actor_type 'api_key' is fine
    assert '[5000 chars]' in line and long_value not in line


def test_web_user_actor(db):
    app = Flask(__name__)
    user = MagicMock(is_authenticated=True)
    user.name = 'qc_user1'
    with app.test_request_context('/qc_done/9/', method='POST'), \
            patch('flask_login.current_user', user):
        audit.record('update', 'folder', 'qc_decision', folder_ref=9, note='QC Passed')
    row = _row(db)
    assert (row['actor_type'], row['actor'], row['source']) == ('user', 'qc_user1', 'web')
    assert row['note'] == 'QC Passed'


def test_given_context_skips_lookup_and_explicit_ids_win(db):
    ctx = {'project_id': 1, 'folder_ref': '9', 'file_ref': '55', 'project_alias': 'ento',
           'folder_name': 'ENT-1', 'file_name': 'ENT_0001'}
    audit.record('delete', 'file', 'deleted', project_id=2, file_ref=55, context=ctx)
    db.run_query.assert_not_called()
    row = _row(db)
    assert row['file_name'] == 'ENT_0001' and row['folder_ref'] == '9'
    assert row['project_id'] == 2


def test_never_raises_and_logs_failed_event(db, caplog):
    db.query_database_insert.side_effect = RuntimeError('table missing')
    with caplog.at_level(logging.ERROR, logger='osprey_audit'):
        assert audit.record('update', 'file', 'marked_sensitive', file_ref=3) is None
    assert 'audit insert failed' in caplog.text and 'marked_sensitive' in caplog.text


def test_lookup_failure_still_records(db):
    db.run_query.side_effect = RuntimeError('db down')
    audit.record('update', 'folder', 'previews', folder_ref=4, note='1')
    assert _row(db)['folder_ref'] == '4'


def test_unknown_action_is_not_written(db):
    assert audit.record('upsert', 'file', 'x') is None
    db.query_database_insert.assert_not_called()


def test_long_note_is_truncated(db):
    audit.record('update', 'folder', 'status_error', folder_ref=1, note='e' * 400)
    assert len(_row(db)['note']) == 255


# --- call sites -------------------------------------------------------------

def test_validate_api_key_sets_audit_actor():
    from api import auth
    app = Flask(__name__)
    rows = [{'api_key': KEY, 'is_admin': 1, 'api_user': 'worker_01', 'not_expired': 1}]
    with app.test_request_context('/api/update/x', method='POST'), \
            patch.object(auth, 'run_query', return_value=rows), \
            patch.object(auth, 'query_database_insert'):
        assert auth.validate_api_key(KEY) == (True, True)
        assert g.api_actor == 'worker_01'


def test_mark_file_sensitive_is_audited():
    from osprey.services import files
    with patch.object(files, 'query_database_insert'), patch.object(audit, 'record') as rec:
        files.mark_file_sensitive(554321, 'label has an address', 3)
    rec.assert_called_once_with('update', 'file', 'marked_sensitive', file_ref=554321)


@pytest.fixture()
def client():
    pytest.importorskip('flask_wtf')
    from app import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app.test_client()


def _post_update(client, data, run_query):
    from api.routes import worker
    with patch.object(worker, 'validate_api_key', return_value=(True, True)), \
            patch.object(worker, 'run_query', run_query), \
            patch.object(worker, 'query_database_insert', return_value=True), \
            patch.object(worker.folder_stats_service, 'recalculate_project_stats'):
        return client.post('/api/update/ento', data=dict(api_key=KEY, **data))


def test_worker_folder_status_error_is_audited(client):
    rq = MagicMock(return_value=[{'project_id': 101, 'transcription': 0}])
    with patch.object(audit, 'record') as rec:
        resp = _post_update(client, {'type': 'folder', 'property': 'status1',
                                     'value': '3 files with errors', 'folder_id': '9876'}, rq)
    assert resp.status_code == 200
    rec.assert_called_once_with('update', 'folder', 'status_error', project_id=101,
                                folder_ref='9876', transcription=False,
                                note='3 files with errors')


def test_worker_badge_only_update_is_not_audited(client):
    rq = MagicMock(return_value=[{'project_id': 101, 'transcription': 0}])
    with patch.object(audit, 'record') as rec:
        resp = _post_update(client, {'type': 'folder', 'property': 'raw1',
                                     'value': 'raw', 'folder_id': '9876'}, rq)
    assert resp.status_code == 200
    rec.assert_not_called()


def test_worker_file_delete_looks_up_names_first(client):
    calls = []
    rq = MagicMock(side_effect=lambda q, *a, **k: calls.append(q) or (
        [{'project_id': 101, 'transcription': 0}] if q.startswith('SELECT') else True))
    ctx = {'file_name': 'ENT0412_0068'}

    def lookup(**kwargs):
        assert not any(q.startswith('DELETE FROM files') for q in calls)
        return ctx

    with patch.object(audit, 'lookup_context', side_effect=lookup) as lk, \
            patch.object(audit, 'record') as rec:
        resp = _post_update(client, {'type': 'file', 'property': 'delete', 'value': '1',
                                     'file_id': '554388', 'folder_id': '9876'}, rq)
    assert resp.status_code == 200
    lk.assert_called_once()
    assert any(q.startswith('DELETE FROM files') for q in calls)
    rec.assert_called_once_with('delete', 'file', 'deleted', project_id=101, folder_ref='9876',
                                file_ref='554388', transcription=False, context=ctx)
