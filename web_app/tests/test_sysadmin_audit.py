"""Sysadmin Audit page: filters, paging, log lookup and rendering."""

import datetime
import gzip
from unittest.mock import patch

import pytest

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')

from werkzeug.datastructures import MultiDict

import settings
from app import app
from osprey.services import sysadmin_audit

ROW = {
    'audit_id': 5139, 'event_at': datetime.datetime(2026, 11, 4, 9, 30, 40, 17000),
    'actor_type': 'api_key', 'actor': 'worker_01', 'source': 'api', 'action': 'delete',
    'entity': 'file', 'event': 'deleted', 'transcription': 0, 'project_id': 101,
    'folder_ref': '9876', 'file_ref': '554388', 'project_alias': 'ento_2026',
    'folder_name': 'ENT-0412', 'file_name': '<b>ENT0412_0068</b>', 'note': None,
    'request_id': 'c7d2' * 8,
}


# ---- service -------------------------------------------------------------

def test_parse_filters_drops_invalid_values():
    f = sysadmin_audit.parse_filters(MultiDict({
        'project_id': 'abc', 'entity': 'user', 'action': 'delete', 'since': '2026-13-01',
        'until': '2026-11-04', 'before': '-5', 'actor': '  worker_01 ', 'q': ''}))
    assert f['project_id'] is None and f['entity'] is None and f['before'] is None
    assert f['action'] == 'delete' and f['actor'] == 'worker_01' and f['q'] is None
    assert f['since'] is None and f['until'] == datetime.date(2026, 11, 4)


def _events(filters, rows):
    with patch.object(sysadmin_audit, 'existing_tables', return_value={'audit_log'}), \
            patch.object(sysadmin_audit.db, 'run_query', return_value=rows) as rq:
        return sysadmin_audit.events(filters), rq


def test_events_query_uses_filters_and_keyset():
    filters = sysadmin_audit.parse_filters(MultiDict({
        'project_id': '101', 'folder_ref': '9876', 'q': '50%_off', 'until': '2026-11-04',
        'before': '6000'}))
    result, rq = _events(filters, [])
    query, params = rq.call_args[0]
    assert 'project_id = %(project_id)s' in query and 'folder_ref = %(folder_ref)s' in query
    assert 'audit_id < %(before)s' in query and 'ORDER BY audit_id DESC' in query
    assert params['q'] == '%50\\%\\_off%'  # LIKE wildcards in the search are literal
    assert params['until'] == datetime.date(2026, 11, 5)  # "To" date is inclusive
    assert params['limit'] == sysadmin_audit.PAGE_SIZE + 1
    assert result['next_before'] is None


def test_events_next_page_cursor():
    rows = [dict(ROW, audit_id=i) for i in range(500, 500 - sysadmin_audit.PAGE_SIZE - 1, -1)]
    result, _ = _events(sysadmin_audit.parse_filters(MultiDict()), rows)
    assert len(result['rows']) == sysadmin_audit.PAGE_SIZE
    assert result['next_before'] == result['rows'][-1]['audit_id']


def test_events_without_table():
    with patch.object(sysadmin_audit, 'existing_tables', return_value=set()):
        assert sysadmin_audit.events({}) == {'table_present': False}


def test_log_details_searches_rotated_gzip(tmp_path):
    current = tmp_path / 'ospreyaudit.log'
    current.write_text('INFO | x | audit_id=51390 request_id=a details={}\n')
    rotated = tmp_path / 'ospreyaudit.log.2.gz'
    with gzip.open(rotated, 'wt') as fh:
        fh.write('INFO | x | audit_id=5139 request_id=c7d2 delete file deleted '
                 'details={"file_id": "554388", "property": "delete"}\n')
    with patch.object(sysadmin_audit, '_log_files', return_value=[str(current), str(rotated)]):
        found = sysadmin_audit.log_details(5139)
        missing = sysadmin_audit.log_details(42)
    assert found['found'] and found['file'] == 'ospreyaudit.log.2.gz'
    assert found['details'] == {'file_id': '554388', 'property': 'delete'}
    assert not missing['found'] and missing['files_searched'] == 2


# ---- pages ---------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    monkeypatch.setattr(app, 'secret_key', 'test-only-not-a-secret')
    monkeypatch.setattr('app.run_query', lambda q, p=None: [
        {'username': 'alice', 'user_id': 1, 'user_active': 1, 'full_name': 'Alice'}])
    monkeypatch.setattr(settings, 'site_net', 'internal')
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = 'alice'
        sess['_fresh'] = True
    return c


def _get(client, url, events=None, admin=True, event=ROW, log=None):
    events = events if events is not None else {
        'table_present': True, 'rows': [ROW], 'next_before': 5000, 'page_size': 100}
    log = log or {'found': True, 'file': 'ospreyaudit.log', 'line': 'INFO | audit_id=5139 <x>',
                  'details': {'file_id': '554388', 'note': '<script>'}, 'files_searched': 1}
    with patch('web.sysadmin.user_perms', return_value=admin), \
            patch.object(sysadmin_audit, 'events', return_value=events) as ev, \
            patch.object(sysadmin_audit, 'filter_options', return_value={
                'projects': [{'project_id': 101, 'project_alias': 'ento_2026', 'project_title': 'E'}],
                'actors': [{'actor': 'worker_01', 'actor_type': 'api_key'}]}), \
            patch.object(sysadmin_audit, 'event', return_value=event), \
            patch.object(sysadmin_audit, 'log_details', return_value=log):
        return client.get(url), ev


def test_audit_page_lists_events(client):
    response, ev = _get(client, '/sysadmin/audit/?project_id=101&entity=file')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'aria-current="page"' in body and 'Audit log' in body
    assert '2026-11-04 09:30:40' in body and 'worker_01' in body
    assert '&lt;b&gt;ENT0412_0068&lt;/b&gt;' in body  # names are escaped
    # Folder link narrows to the folder and keeps the current filters.
    assert 'folder_ref=9876' in body and 'project_id=101' in body
    assert 'before=5000' in body  # "Older" link
    assert '/sysadmin/audit/5139/' in body
    assert ev.call_args[0][0]['entity'] == 'file'


def test_audit_page_without_table(client):
    response, _ = _get(client, '/sysadmin/audit/', events={'table_present': False})
    assert response.status_code == 200
    assert 'db/audit_log.sql' in response.get_data(as_text=True)


def test_audit_page_requires_sysadmin(client):
    response, _ = _get(client, '/sysadmin/audit/', admin=False)
    assert response.status_code == 302 and response.headers['Location'].endswith('/home/')
    response, _ = _get(client, '/sysadmin/audit/5139/', admin=False)
    assert response.status_code == 302


def test_audit_event_page_shows_log_details(client):
    response, _ = _get(client, '/sysadmin/audit/5139/')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Audit event 5139' in body and '554388' in body
    assert '&lt;script&gt;' in body and '<script>' not in body.split('Details from')[1]
    assert 'request_id=' + 'c7d2' * 8 in body


def test_audit_event_unknown_is_404(client):
    response, _ = _get(client, '/sysadmin/audit/1/', event=None)
    assert response.status_code == 404
