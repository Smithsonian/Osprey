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
