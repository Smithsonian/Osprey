"""Site-wide view plumbing: template context, the error page, and the API-site redirect.

Covers the app-level hooks that replaced per-route boilerplate
(inject_site_context, render_error, redirect_web_routes_on_api_site).
No database access: every request below is answered before any query runs.
"""

import pytest

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')

import app as app_module
from app import app


@pytest.fixture(autouse=True)
def secret_key(monkeypatch):
    # base.html calls csrf_token(), which needs a session; settings.py.template has no key
    monkeypatch.setattr(app, 'secret_key', 'test-only-key')


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app.test_client()


def test_site_context_has_site_vars():
    ctx = app_module.inject_site_context()
    assert set(ctx) == {'site_env', 'site_net', 'site_ver', 'analytics_code'}
    assert ctx['site_ver'] == app_module.site_ver


def test_render_error_returns_status_and_message():
    from web.errors import render_error

    with app.test_request_context():
        body, status = render_error('Something broke', 418)
    assert status == 418
    assert 'Something broke' in body


def test_unknown_url_uses_error_page(client):
    response = client.get('/no/such/page/')
    assert response.status_code == 404
    assert b'Error:' in response.data


def test_api_site_redirects_web_routes(client, monkeypatch):
    monkeypatch.setattr(app_module, 'site_net', 'api')
    response = client.get('/about/')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/api/')


def test_api_site_redirects_previously_unguarded_route(client, monkeypatch):
    # /logout had no guard before the before_request hook existed
    monkeypatch.setattr(app_module, 'site_net', 'api')
    response = client.get('/logout')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/api/')


def test_api_site_keeps_api_and_404(client, monkeypatch):
    monkeypatch.setattr(app_module, 'site_net', 'api')
    # API blueprint is not redirected (405: GET on a POST-only worker route)
    assert client.get('/api/update/some_project').status_code == 405
    # Unmatched URLs still 404 instead of bouncing to the route list
    assert client.get('/no/such/page/').status_code == 404
