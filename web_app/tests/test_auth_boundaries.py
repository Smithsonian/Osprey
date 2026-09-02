"""Request-level checks of the authentication boundaries.

These need Flask (and friends) installed but no database: every assertion
targets behavior that happens before any query runs. Derived from the
manual checklist in tests/WORKER_SMOKE_TEST.md.
"""

import pytest

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')

from app import app


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    # CSRF is exercised in production config; here we test the auth gates.
    app.config['WTF_CSRF_ENABLED'] = False
    return app.test_client()


def test_worker_update_rejects_get(client):
    assert client.get('/api/update/some_project').status_code == 405


def test_worker_new_rejects_get(client):
    assert client.get('/api/new/some_project').status_code == 405


def test_worker_update_requires_api_key(client):
    response = client.post('/api/update/some_project', data={})
    assert response.status_code == 400
    assert 'api_key' in response.get_json()['error']


def test_worker_new_requires_api_key(client):
    response = client.post('/api/new/some_project', data={})
    assert response.status_code == 400
    assert 'api_key' in response.get_json()['error']


def test_report_refresh_requires_login(client):
    response = client.post('/reports/demo/42/refresh')
    # Anonymous callers are redirected to login (or 401 with no login view);
    # they must never reach the queueing logic.
    assert response.status_code in (301, 302, 401)
