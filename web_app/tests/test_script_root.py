"""settings.app_root is applied as the WSGI script root (web/script_root.py)."""

from flask import Flask, request, url_for

from web.script_root import ScriptRootMiddleware, normalize_prefix


def _client(prefix):
    app = Flask(__name__)

    @app.route('/page/')
    def page():
        return '{}|{}'.format(request.script_root, url_for('page'))

    app.wsgi_app = ScriptRootMiddleware(app.wsgi_app, prefix)
    return app.test_client()


def test_normalize_prefix():
    assert normalize_prefix('') == ''
    assert normalize_prefix(None) == ''
    assert normalize_prefix('/') == ''
    assert normalize_prefix('osprey') == '/osprey'
    assert normalize_prefix('/osprey/') == '/osprey'
    assert normalize_prefix('/a/b/') == '/a/b'


def test_no_prefix_is_a_no_op():
    resp = _client('').get('/page/')
    assert resp.get_data(as_text=True) == '|/page/'


def test_prefix_kept_by_proxy_is_stripped():
    resp = _client('/osprey').get('/osprey/page/')
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == '/osprey|/osprey/page/'


def test_prefix_already_stripped_by_proxy():
    resp = _client('/osprey').get('/page/')
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == '/osprey|/osprey/page/'


def test_prefix_only_matches_whole_segment():
    # '/ospreyx/...' is not under '/osprey'
    assert _client('/osprey').get('/ospreyx/page/').status_code == 404


def test_bare_prefix_maps_to_root():
    app = Flask(__name__)

    @app.route('/')
    def index():
        return url_for('static', filename='a.css')

    app.wsgi_app = ScriptRootMiddleware(app.wsgi_app, 'osprey/')
    resp = app.test_client().get('/osprey')
    assert resp.get_data(as_text=True) == '/osprey/static/a.css'
