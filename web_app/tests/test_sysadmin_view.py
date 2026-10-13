"""Access rules for the /sysadmin/ page.

Only a user with users.sysadmin = 1, on a site_net == "internal"
deployment, may see it; everyone else is redirected to /home/.
"""

from unittest.mock import patch

import pytest

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')

import settings
from app import app

STATUS = {
    'app': {'ok': True, 'data': {'version': 'x', 'env': 'dev', 'site_net': 'internal',
                                 'python': '3.9', 'host': 'h', 'packages': {}}},
    'db': {'ok': False, 'error': 'OperationalError: down'},
    'cache': {'ok': True, 'data': {'dir': '/c', 'files': 1, 'bytes': 10}},
    'reports': {'ok': True, 'data': {'table_present': False}},
    'logs': {'ok': True, 'data': [{'path': '/l/ospreyapp.log', 'exists': True, 'size': 5,
                                   'lines': ['ERROR | boom <script>']}]},
}


@pytest.fixture()
def client(monkeypatch):
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    # settings.py.template leaves SECRET_KEY empty; sessions need one.
    monkeypatch.setattr(app, 'secret_key', 'test-only-not-a-secret')
    # load_user() looks the session's username up in the users table.
    monkeypatch.setattr('app.run_query', lambda q, p=None: [
        {'username': 'alice', 'user_id': 1, 'user_active': 1, 'full_name': 'Alice'}])
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = 'alice'
        sess['_fresh'] = True
    return c


def _get(client, site_net, is_sysadmin, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', site_net)
    with patch('web.sysadmin.user_perms', return_value=is_sysadmin) as perms, \
            patch('web.sysadmin.system_status.collect', return_value=STATUS):
        return client.get('/sysadmin/'), perms


def test_sysadmin_internal_sees_page(client, monkeypatch):
    response, perms = _get(client, 'internal', True, monkeypatch)
    assert response.status_code == 200
    perms.assert_called_once_with('', user_type='sysadmin')
    body = response.get_data(as_text=True)
    assert 'System Admin' in body
    assert 'Unavailable: OperationalError: down' in body
    # Log lines are escaped, not rendered as HTML.
    assert '&lt;script&gt;' in body and '<script>' not in body.split('ERROR | boom')[1][:20]


def test_non_sysadmin_redirected_home(client, monkeypatch):
    response, _ = _get(client, 'internal', False, monkeypatch)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/home/')


@pytest.mark.parametrize('site_net', ['external', 'api'])
def test_sysadmin_on_non_internal_site_redirected_home(client, monkeypatch, site_net):
    # Exercises the view's own gate. (On a real api site, app.py's
    # before_request sends web routes to the API index before this runs.)
    response, perms = _get(client, site_net, True, monkeypatch)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/home/')
    # The flag is never queried off the internal site.
    perms.assert_not_called()


SUBPAGES = {
    '/sysadmin/schema/': {'schema_status': [{'file': 'db/kiosk.sql', 'target': 'kiosk', 'applied': True}],
                          'table_sizes': [{'name': 'files', 'est_rows': 10, 'data_bytes': 1, 'index_bytes': 1,
                                           'total_bytes': 2, 'update_time': None}],
                          'stats': {'table_present': True, 'jobs': [{
                              'job_id': 'files_exif', 'title': 'files_exif rows by project', 'note': 'n',
                              'stats': [('files_exif_rows', 'EXIF rows'), ('files_exif_files', 'Files with EXIF')],
                              'computed_at': None, 'totals': {'files_exif_rows': 150, 'files_exif_files': 3},
                              'run': {'status': 'failed', 'last_failed_at': None, 'error_message': 'boom',
                                      'duration_ms': 1000},
                              'projects': [
                                  {'project_id': 10, 'project_alias': 'p', 'project_title': 'P',
                                   'project_status': 'Ongoing',
                                   'values': {'files_exif_rows': 100, 'files_exif_files': 2}},
                                  {'project_id': 11, 'project_alias': None, 'project_title': 'No alias',
                                   'project_status': None, 'values': {'files_exif_rows': 40}},
                                  {'project_id': 0, 'project_alias': None, 'project_title': None,
                                   'project_status': None, 'values': {'files_exif_rows': 10,
                                                                      'files_exif_files': 1}}]}]}},
    '/sysadmin/users/': {'users': [{'user_id': 1, 'username': 'alice', 'full_name': 'A', 'email': 'a@x',
                                    'user_active': 1, 'is_admin': 0, 'sysadmin': 1, 'internal': 1,
                                    'project_count': 1, 'updated_at': None}],
                         # Second project has no alias (projects.project_alias is nullable):
                         # it must render as text, not raise BuildError for url_for('dashboard').
                         'assignments_by_user': {1: [{'project_alias': 'p', 'project_title': 'P',
                                                      'project_status': None},
                                                     {'project_alias': None, 'project_title': 'No Alias',
                                                      'project_status': None}]}},
    '/sysadmin/projects/': {'projects_overview': [{'project_id': 1, 'project_alias': 'p', 'project_title': 'P',
                                                   'project_status': 'Ongoing', 'project_unit': 'U',
                                                   'qc_status': 1, 'users': [], 'settings': {'c': ['md5']}}],
                            'transcription_profile_config': None},
    '/sysadmin/api-keys/': {'api_keys': {'keys': [{'key_masked': '…abcd', 'api_user': 'w', 'is_active': 1,
                                                   'is_admin': 0, 'expires_on': None, 'expired': 1,
                                                   'usage_rate': 1, 'last_used': None, 'calls_24h': 0}],
                                         'invalid': [], 'window': 100}},
    '/sysadmin/kiosks/': {'kiosks': {'table_present': True, 'days': 30, 'machines': [],
                                     'configured_not_seen': ['1.2.3.4']}},
    '/sysadmin/reports/': {'reports': {'materializations': True, 'rows': [
        {'report_id': 'r', 'project_id': 1, 'project_alias': 'p', 'report_title': 'R', 'pregenerated': 1,
         'updated_at': None, 'status': 'failed', 'last_succeeded_at': None, 'duration_ms': 1500,
         'row_count': 1234}]}},
}


@pytest.mark.parametrize('url', sorted(SUBPAGES))
def test_subpages_render_for_sysadmin(client, monkeypatch, url):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    for func, value in SUBPAGES[url].items():
        monkeypatch.setattr('osprey.services.sysadmin_data.' + func, lambda value=value: value)
    with patch('web.sysadmin.user_perms', return_value=True):
        response = client.get(url)
    assert response.status_code == 200, response.get_data(as_text=True)[:500]
    assert 'aria-current="page"' in response.get_data(as_text=True)


@pytest.mark.parametrize('url', sorted(SUBPAGES))
def test_subpages_redirect_non_sysadmin(client, monkeypatch, url):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    with patch('web.sysadmin.user_perms', return_value=False):
        response = client.get(url)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/home/')


@pytest.mark.parametrize('url', sorted(SUBPAGES))
def test_subpages_redirect_on_external_site(client, monkeypatch, url):
    monkeypatch.setattr(settings, 'site_net', 'external')
    with patch('web.sysadmin.user_perms', return_value=True) as perms:
        response = client.get(url)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/home/')
    perms.assert_not_called()


# ---- POST actions -------------------------------------------------------

REPORT = {'project_id': 10, 'report_id': 'bot_full', 'pregenerated': 1}


def _post(client, monkeypatch, url, is_sysadmin=True, site_net='internal'):
    monkeypatch.setattr(settings, 'site_net', site_net)
    with patch('web.sysadmin.user_perms', return_value=is_sysadmin):
        return client.post(url)


def test_requeue_queues_pregenerated_report(client, monkeypatch):
    with patch('web.sysadmin.report_service.get_project_report', return_value=REPORT) as get, \
            patch('web.sysadmin.report_service.request_pregenerated_refresh', return_value=True) as req:
        response = _post(client, monkeypatch, '/sysadmin/reports/10/bot_full/requeue')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/sysadmin/reports/')
    get.assert_called_once_with(10, 'bot_full')
    req.assert_called_once_with(REPORT, requested_by='alice')
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'success'


def test_requeue_refuses_live_report(client, monkeypatch):
    live = dict(REPORT, pregenerated=0)
    with patch('web.sysadmin.report_service.get_project_report', return_value=live), \
            patch('web.sysadmin.report_service.request_pregenerated_refresh') as req:
        response = _post(client, monkeypatch, '/sysadmin/reports/10/bot_full/requeue')
    assert response.status_code == 302
    req.assert_not_called()


def test_requeue_unknown_report(client, monkeypatch):
    with patch('web.sysadmin.report_service.get_project_report', return_value=None), \
            patch('web.sysadmin.report_service.request_pregenerated_refresh') as req:
        _post(client, monkeypatch, '/sysadmin/reports/10/nope/requeue')
    req.assert_not_called()
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'danger'


def test_requeue_db_error_is_reported_not_500(client, monkeypatch):
    with patch('web.sysadmin.report_service.get_project_report', return_value=REPORT), \
            patch('web.sysadmin.report_service.request_pregenerated_refresh', side_effect=RuntimeError('db')):
        response = _post(client, monkeypatch, '/sysadmin/reports/10/bot_full/requeue')
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'danger'


def test_clear_cache(client, monkeypatch):
    with patch('web.sysadmin.cache.clear', return_value=True) as clear:
        response = _post(client, monkeypatch, '/sysadmin/cache/clear')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/sysadmin/')
    clear.assert_called_once_with()


@pytest.mark.parametrize('url', ['/sysadmin/cache/clear', '/sysadmin/reports/10/bot_full/requeue'])
@pytest.mark.parametrize('is_sysadmin,site_net', [(False, 'internal'), (True, 'external')])
def test_actions_gated(client, monkeypatch, url, is_sysadmin, site_net):
    with patch('web.sysadmin.cache.clear') as clear, \
            patch('web.sysadmin.report_service.request_pregenerated_refresh') as req:
        response = _post(client, monkeypatch, url, is_sysadmin=is_sysadmin, site_net=site_net)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/home/')
    clear.assert_not_called()
    req.assert_not_called()


@pytest.mark.parametrize('url', ['/sysadmin/cache/clear', '/sysadmin/reports/10/bot_full/requeue'])
def test_actions_reject_get(client, monkeypatch, url):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    with patch('web.sysadmin.user_perms', return_value=True):
        assert client.get(url).status_code == 405


@pytest.mark.parametrize('url', ['/sysadmin/cache/clear', '/sysadmin/reports/10/bot_full/requeue'])
def test_actions_require_csrf_token(client, monkeypatch, url):
    # The fixture disables CSRF; production has it on.
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    with patch('web.sysadmin.cache.clear') as clear, \
            patch('web.sysadmin.report_service.request_pregenerated_refresh') as req:
        response = _post(client, monkeypatch, url)
    assert response.status_code == 400
    clear.assert_not_called()
    req.assert_not_called()


# ---- Generate Reports -----------------------------------------------------

LIVE = {'report_id': 'live1', 'project_id': None, 'title': 'Live one', 'description': 'd',
        'query': 'SELECT 1 AS a', 'pregenerated': 0, 'project_title': None, 'project_alias': None}
PREGEN = dict(LIVE, report_id='big1', title='Big one', pregenerated=1, project_id=10, project_title='P')


def _gen(monkeypatch, report=LIVE):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    monkeypatch.setattr('osprey.services.sysadmin_reports.table_exists', lambda: True)
    monkeypatch.setattr('osprey.services.sysadmin_reports.get_report',
                        lambda rid: report if rid == report['report_id'] else None)


def test_generate_list_renders(client, monkeypatch):
    _gen(monkeypatch)
    groups = [{'project_id': None, 'project_title': None, 'project_alias': None,
               'reports': [dict(LIVE, status=None)]},
              {'project_id': 10, 'project_title': 'P', 'project_alias': 'p',
               'reports': [dict(PREGEN, status='succeeded', last_succeeded_at=None, row_count=5, duration_ms=10,
                                artifact_path_csv='big1_x.csv', artifact_path_xlsx=None)]}]
    monkeypatch.setattr('osprey.services.sysadmin_reports.list_reports', lambda: groups)
    with patch('web.sysadmin.user_perms', return_value=True):
        body = client.get('/sysadmin/generate/').get_data(as_text=True)
    assert 'All projects' in body and 'Live one' in body and 'Big one' in body
    assert '/sysadmin/generate/live1/' in body and '/sysadmin/generate/big1/queue' in body
    assert '/sysadmin/generate/big1/file/csv' in body and '/file/xlsx' not in body


def test_generate_list_without_table(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    monkeypatch.setattr('osprey.services.sysadmin_reports.table_exists', lambda: False)
    with patch('web.sysadmin.user_perms', return_value=True):
        body = client.get('/sysadmin/generate/').get_data(as_text=True)
    assert 'db/sysadmin_reports.sql' in body


def test_generate_run_live_shows_rows(client, monkeypatch):
    _gen(monkeypatch)
    result = {'columns': ['a'], 'rows': [{'a': '<b>x</b>'}], 'total': 1, 'duration_ms': 5}
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_reports.run_live', return_value=result):
        r = client.get('/sysadmin/generate/live1/')
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and '&lt;b&gt;x&lt;/b&gt;' in body and '1 row ' in body


def test_generate_run_unsafe_query_flashes(client, monkeypatch):
    _gen(monkeypatch, dict(LIVE, query='DELETE FROM files'))
    with patch('web.sysadmin.user_perms', return_value=True):
        r = client.get('/sysadmin/generate/live1/')
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'danger'


def test_generate_run_db_error_flashes_not_500(client, monkeypatch):
    _gen(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_reports.run_live', side_effect=RuntimeError('db')):
        assert client.get('/sysadmin/generate/live1/').status_code == 302


def test_generate_unknown_report_404(client, monkeypatch):
    _gen(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True):
        assert client.get('/sysadmin/generate/nope/').status_code == 404


def test_generate_download_live_csv(client, monkeypatch):
    _gen(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_reports.live_csv', return_value='a\n1\n'):
        r = client.get('/sysadmin/generate/live1/download.csv')
    assert r.status_code == 200 and r.mimetype == 'text/csv' and r.get_data(as_text=True) == 'a\n1\n'
    assert 'live1.csv' in r.headers['Content-Disposition']


def test_generate_queue_pregenerated(client, monkeypatch):
    _gen(monkeypatch, PREGEN)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_reports.queue', return_value=True) as q:
        r = client.post('/sysadmin/generate/big1/queue')
    assert r.status_code == 302 and r.headers['Location'].endswith('/sysadmin/generate/')
    q.assert_called_once_with(PREGEN, requested_by='alice')


def test_generate_queue_refuses_live(client, monkeypatch):
    _gen(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_reports.queue') as q:
        client.post('/sysadmin/generate/live1/queue')
    q.assert_not_called()


def test_generate_file_served_from_artifact_dir(client, monkeypatch, tmp_path):
    _gen(monkeypatch, PREGEN)
    monkeypatch.setattr('osprey.services.sysadmin_reports.ARTIFACT_DIR', str(tmp_path))
    (tmp_path / 'big1_20261013_020000.csv').write_text('a\n1\n')
    status = {'artifact_path_csv': 'big1_20261013_020000.csv', 'artifact_path_xlsx': None}
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.materializations.get_materialization', return_value=status) as gm:
        r = client.get('/sysadmin/generate/big1/file/csv')
        assert r.status_code == 200 and r.get_data(as_text=True) == 'a\n1\n'
        r.close()
        assert client.get('/sysadmin/generate/big1/file/xlsx').status_code == 302  # no file yet
        assert client.get('/sysadmin/generate/big1/file/exe').status_code == 404
    gm.assert_called_with(0, 'sysrep:big1')


@pytest.mark.parametrize('method,url', [
    ('get', '/sysadmin/generate/'), ('get', '/sysadmin/generate/live1/'),
    ('get', '/sysadmin/generate/live1/download.csv'), ('post', '/sysadmin/generate/big1/queue'),
    ('get', '/sysadmin/generate/big1/file/csv'),
])
@pytest.mark.parametrize('is_sysadmin,site_net', [(False, 'internal'), (True, 'external')])
def test_generate_routes_gated(client, monkeypatch, method, url, is_sysadmin, site_net):
    monkeypatch.setattr(settings, 'site_net', site_net)
    with patch('web.sysadmin.user_perms', return_value=is_sysadmin), \
            patch('web.sysadmin.sysadmin_reports.run_live') as run, \
            patch('web.sysadmin.sysadmin_reports.queue') as q:
        r = getattr(client, method)(url)
    assert r.status_code == 302 and r.headers['Location'].endswith('/home/')
    run.assert_not_called()
    q.assert_not_called()


def test_generate_queue_requires_csrf(client, monkeypatch):
    _gen(monkeypatch, PREGEN)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_reports.queue') as q:
        assert client.post('/sysadmin/generate/big1/queue').status_code == 400
    q.assert_not_called()


def test_generate_file_unreadable_flashes_not_500(client, monkeypatch, tmp_path):
    _gen(monkeypatch, PREGEN)
    monkeypatch.setattr('osprey.services.sysadmin_reports.ARTIFACT_DIR', str(tmp_path))
    (tmp_path / 'big1_20261013_020000.csv').write_text('a\n')
    status = {'artifact_path_csv': 'big1_20261013_020000.csv'}
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.materializations.get_materialization', return_value=status), \
            patch('web.sysadmin.send_file', side_effect=PermissionError('denied')):
        r = client.get('/sysadmin/generate/big1/file/csv')
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'danger'


# ---- Data Entry -----------------------------------------------------------

PROJ = {'project_id': 12, 'project_title': 'Botany', 'project_alias': 'bot', 'project_status': 'Ongoing'}
DTYPE = {'type_id': 'special_folders', 'label': 'Special folders', 'description': 'd', 'value_type': 'text'}


def _data(monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    monkeypatch.setattr('osprey.services.project_custom_data.tables_exist', lambda: True)
    # Projects 12 and 13 exist; special_folders is defined only for 12.
    monkeypatch.setattr('osprey.services.project_custom_data.get_project',
                        lambda pid: dict(PROJ, project_id=pid) if pid in (12, 13) else None)
    monkeypatch.setattr('osprey.services.project_custom_data.get_type',
                        lambda pid, tid: DTYPE if (pid, tid) == (12, 'special_folders') else None)


def test_data_step1_lists_projects_and_redirects(client, monkeypatch):
    _data(monkeypatch)
    monkeypatch.setattr('osprey.services.project_custom_data.list_projects',
                        lambda: [dict(PROJ, n_types=1, n_values=2)])
    with patch('web.sysadmin.user_perms', return_value=True):
        body = client.get('/sysadmin/data/').get_data(as_text=True)
        r = client.get('/sysadmin/data/?project_id=12')
    assert 'Botany' in body and '1 type, 2 values' in body
    assert r.status_code == 302 and r.headers['Location'].endswith('/sysadmin/data/12/')


def test_data_without_tables(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    monkeypatch.setattr('osprey.services.project_custom_data.tables_exist', lambda: False)
    with patch('web.sysadmin.user_perms', return_value=True):
        assert 'db/project_custom_data.sql' in client.get('/sysadmin/data/').get_data(as_text=True)
        assert client.get('/sysadmin/data/12/').status_code == 404


def test_data_step2_lists_types(client, monkeypatch):
    _data(monkeypatch)
    monkeypatch.setattr('osprey.services.project_custom_data.list_types',
                        lambda pid: [dict(DTYPE, n_values=3)])
    with patch('web.sysadmin.user_perms', return_value=True):
        body = client.get('/sysadmin/data/12/').get_data(as_text=True)
        assert client.get('/sysadmin/data/99/').status_code == 404
    assert '/sysadmin/data/12/special_folders/' in body and 'Special folders' in body


def test_data_step3_values_page(client, monkeypatch):
    _data(monkeypatch)
    vals = {'current': [{'value_id': 5, 'value': '<f1>', 'note': None, 'added_by': 'alice', 'added_at': None}],
            'removed': [{'value': 'old', 'added_by': 'a', 'added_at': None, 'removed_by': 'b', 'removed_at': None}]}
    monkeypatch.setattr('osprey.services.project_custom_data.list_values', lambda pid, tid: vals)
    with patch('web.sysadmin.user_perms', return_value=True):
        r = client.get('/sysadmin/data/12/special_folders/')
        assert client.get('/sysadmin/data/12/nope/').status_code == 404
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and '&lt;f1&gt;' in body and 'Removed values (1)' in body
    assert '/sysadmin/data/12/special_folders/5/remove' in body


def test_data_add_saves_and_logs_user(client, monkeypatch):
    _data(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.custom_data.add_values', return_value=2) as add:
        r = client.post('/sysadmin/data/12/special_folders/add', data={'values': 'f1\nf2\n', 'note': ' n '})
    assert r.status_code == 302 and r.headers['Location'].endswith('/sysadmin/data/12/special_folders/')
    add.assert_called_once_with(12, 'special_folders', ['f1', 'f2'], 'n', 'alice')


def test_data_add_invalid_saves_nothing(client, monkeypatch):
    _data(monkeypatch)
    monkeypatch.setitem(DTYPE, 'value_type', 'number')
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.custom_data.add_values') as add:
        client.post('/sysadmin/data/12/special_folders/add', data={'values': '1\nabc'})
    add.assert_not_called()
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'danger'


def test_data_remove(client, monkeypatch):
    _data(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.custom_data.remove_value', return_value=True) as rm:
        r = client.post('/sysadmin/data/12/special_folders/5/remove')
    assert r.status_code == 302
    rm.assert_called_once_with(12, 'special_folders', 5, 'alice')


@pytest.mark.parametrize('method,url', [
    ('get', '/sysadmin/data/'), ('get', '/sysadmin/data/12/'), ('get', '/sysadmin/data/12/special_folders/'),
    ('post', '/sysadmin/data/12/special_folders/add'), ('post', '/sysadmin/data/12/special_folders/5/remove'),
])
@pytest.mark.parametrize('is_sysadmin,site_net', [(False, 'internal'), (True, 'external')])
def test_data_routes_gated(client, monkeypatch, method, url, is_sysadmin, site_net):
    _data(monkeypatch)
    monkeypatch.setattr(settings, 'site_net', site_net)
    with patch('web.sysadmin.user_perms', return_value=is_sysadmin), \
            patch('web.sysadmin.custom_data.add_values') as add, \
            patch('web.sysadmin.custom_data.remove_value') as rm:
        r = getattr(client, method)(url, data={'values': 'x'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/home/')
    add.assert_not_called()
    rm.assert_not_called()


@pytest.mark.parametrize('url', ['/sysadmin/data/12/special_folders/add',
                                 '/sysadmin/data/12/special_folders/5/remove'])
def test_data_writes_require_csrf(client, monkeypatch, url):
    _data(monkeypatch)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.custom_data.add_values') as add, \
            patch('web.sysadmin.custom_data.remove_value') as rm:
        assert client.post(url, data={'values': 'x'}).status_code == 400
    add.assert_not_called()
    rm.assert_not_called()


@pytest.mark.parametrize('method,url', [
    ('get', '/sysadmin/data/13/special_folders/'),
    ('post', '/sysadmin/data/13/special_folders/add'),
    ('post', '/sysadmin/data/13/special_folders/5/remove'),
])
def test_data_other_projects_type_is_404(client, monkeypatch, method, url):
    """Project 13 exists but has no special_folders type: never fall back to 12's."""
    _data(monkeypatch)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.custom_data.add_values') as add, \
            patch('web.sysadmin.custom_data.remove_value') as rm:
        assert getattr(client, method)(url, data={'values': 'x'}).status_code == 404
    add.assert_not_called()
    rm.assert_not_called()


def test_data_step1_no_projects_with_types(client, monkeypatch):
    _data(monkeypatch)
    monkeypatch.setattr('osprey.services.project_custom_data.list_projects', lambda: [])
    with patch('web.sysadmin.user_perms', return_value=True):
        assert 'No project has data types yet' in client.get('/sysadmin/data/').get_data(as_text=True)


# ---- Users: set inactive ----------------------------------------------------

USERS = [
    {'user_id': 1, 'username': 'alice', 'full_name': 'Alice', 'email': 'a@x', 'user_active': 1, 'is_admin': 0,
     'sysadmin': 1, 'internal': 1, 'project_count': 0, 'updated_at': None},
    {'user_id': 2, 'username': 'bob', 'full_name': '<Bob>', 'email': 'b@x', 'user_active': 1, 'is_admin': 0,
     'sysadmin': 0, 'internal': 1, 'project_count': 3, 'updated_at': None},
    {'user_id': 3, 'username': 'carol', 'full_name': 'Carol', 'email': 'c@x', 'user_active': 0, 'is_admin': 0,
     'sysadmin': 0, 'internal': 1, 'project_count': 0, 'updated_at': None},
]


def test_users_page_buttons_only_for_other_active_users(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    monkeypatch.setattr('osprey.services.sysadmin_data.users', lambda: USERS)
    monkeypatch.setattr('osprey.services.sysadmin_data.assignments_by_user', lambda: {})
    with patch('web.sysadmin.user_perms', return_value=True):
        body = client.get('/sysadmin/users/').get_data(as_text=True)
    assert '/sysadmin/users/2/deactivate' in body          # bob: active, not me
    assert '/sysadmin/users/1/deactivate' not in body      # alice: the signed-in sysadmin
    assert '/sysadmin/users/3/deactivate' not in body      # carol: already inactive
    assert 'id="deactivateModal"' in body and 'data-fullname="&lt;Bob&gt;"' in body


def test_deactivate_user_ok(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_users.deactivate_user', return_value=('ok', 'bob')) as d:
        r = client.post('/sysadmin/users/2/deactivate')
    assert r.status_code == 302 and r.headers['Location'].endswith('/sysadmin/users/')
    d.assert_called_once_with(2, 'alice')
    with client.session_transaction() as sess:
        assert sess['_flashes'][0] == ('success', 'bob is now inactive and can no longer log in.')


def test_deactivate_self_refused_message(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_users.deactivate_user', return_value=('self', 'alice')):
        client.post('/sysadmin/users/1/deactivate')
    with client.session_transaction() as sess:
        assert sess['_flashes'][0][0] == 'danger'


def test_deactivate_db_error_flashes_not_500(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_users.deactivate_user', side_effect=RuntimeError('db')):
        assert client.post('/sysadmin/users/2/deactivate').status_code == 302


@pytest.mark.parametrize('is_sysadmin,site_net', [(False, 'internal'), (True, 'external')])
def test_deactivate_gated(client, monkeypatch, is_sysadmin, site_net):
    monkeypatch.setattr(settings, 'site_net', site_net)
    with patch('web.sysadmin.user_perms', return_value=is_sysadmin), \
            patch('web.sysadmin.sysadmin_users.deactivate_user') as d:
        r = client.post('/sysadmin/users/2/deactivate')
    assert r.status_code == 302 and r.headers['Location'].endswith('/home/')
    d.assert_not_called()


def test_deactivate_rejects_get_and_missing_csrf(client, monkeypatch):
    monkeypatch.setattr(settings, 'site_net', 'internal')
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    with patch('web.sysadmin.user_perms', return_value=True), \
            patch('web.sysadmin.sysadmin_users.deactivate_user') as d:
        assert client.get('/sysadmin/users/2/deactivate').status_code == 405
        assert client.post('/sysadmin/users/2/deactivate').status_code == 400
    d.assert_not_called()
