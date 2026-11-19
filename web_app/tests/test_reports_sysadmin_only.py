"""data_reports.sysadmin_only: hidden from non-sysadmins on the web and from the API,
and pregenerated files kept out of static/."""

import os
from unittest.mock import patch

import pytest

pytest.importorskip('flask')
pytest.importorskip('flask_login')
pytest.importorskip('flask_wtf')
pytest.importorskip('pandas')

from app import app
from osprey.services import projects as project_service
from osprey.services import reports as rs
from osprey.services import sysadmin_reports as sr

PUBLIC = {'report_id': 'pub', 'project_id': 7, 'report_title': 'Public', 'pregenerated': 0,
          'sysadmin_only': 0}
PRIVATE = {'report_id': 'priv', 'project_id': 7, 'report_title': 'Private', 'pregenerated': 1,
           'sysadmin_only': 1}
# Row shape before db/data_reports_sysadmin_only.sql is applied.
LEGACY = {'report_id': 'old', 'project_id': 7, 'report_title': 'Old', 'pregenerated': 0}


@pytest.fixture()
def client(monkeypatch):
    app.config['TESTING'] = True
    monkeypatch.setattr(app, 'secret_key', 'test-only-not-a-secret')
    return app.test_client()


# ---- services -------------------------------------------------------------

def test_list_hides_sysadmin_only_unless_asked():
    rows = [PUBLIC, PRIVATE, LEGACY]
    with patch.object(rs.builtin_reports, 'list_project_reports', return_value=rows):
        assert [r['report_id'] for r in rs.list_project_reports(7)] == ['pub', 'old']
        assert rs.list_project_reports(7, include_sysadmin_only=True) == rows


def test_api_lookup_never_returns_sysadmin_only():
    with patch.object(rs, 'run_query', return_value=[PRIVATE]):
        assert rs.get_report('priv') == []
    with patch.object(rs, 'run_query', return_value=[LEGACY]):
        assert rs.get_report('old') == [LEGACY]


def test_api_project_details_leave_out_sysadmin_only():
    def rq(query, params=None):
        if 'data_reports' in query:
            return [PUBLIC, PRIVATE, LEGACY]
        if 'projects_stats' in query:
            return [{}]
        return []

    with patch.object(project_service, 'run_query', side_effect=rq), \
            patch.object(project_service.folder_service, 'list_for_project_api', return_value=[]):
        row = project_service.enrich_project_details({'project_id': 7, 'transcription': 0})
    assert row['reports'] == [{'report_id': 'pub', 'report_title': 'Public'},
                              {'report_id': 'old', 'report_title': 'Old'}]


def test_artifact_file_keeps_sysadmin_only_out_of_static(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, 'ARTIFACT_DIR', str(tmp_path))
    name = rs.private_artifact_base(7, 'priv') + '_20261013_020000.csv'
    (tmp_path / name).write_text('a\n1\n')

    assert rs.artifact_file(PRIVATE, {'artifact_path_csv': name}, 'csv') == (
        'private', os.path.realpath(tmp_path / name))
    # A file from a run before the report was restricted is not offered.
    assert rs.artifact_file(PRIVATE, {'artifact_path_csv': 'reports/report_priv_x.csv'}, 'csv') is None
    # Another report's private file, a path escape, and a missing format.
    other = rs.private_artifact_base(7, 'other') + '_20261013_020000.csv'
    (tmp_path / other).write_text('a\n')
    assert rs.artifact_file(PRIVATE, {'artifact_path_csv': other}, 'csv') is None
    assert rs.artifact_file(PRIVATE, {'artifact_path_csv': '../settings.py'}, 'csv') is None
    assert rs.artifact_file(PRIVATE, {'artifact_path_csv': name}, 'xlsx') is None
    assert rs.artifact_file(PRIVATE, None, 'csv') is None

    public = dict(PUBLIC, pregenerated=1)
    assert rs.artifact_file(public, {'artifact_path_csv': 'reports/report_pub_x.csv'}, 'csv') == (
        'static', 'reports/report_pub_x.csv')


def test_private_names_cannot_collide_with_sysadmin_reports():
    assert not sr.REPORT_ID_RE.match(rs.private_artifact_base(7, 'priv'))
    assert rs.private_artifact_base(7, '../x y') == 'data.7._x_y'


# ---- web routes -----------------------------------------------------------

def _routes(client, report, allowed, path):
    with patch('web.reports.report_service.get_project_id', return_value=7), \
            patch('web.reports.report_service.get_project_report', return_value=report), \
            patch('web.reports.sysadmin_allowed', return_value=allowed), \
            patch('web.reports.report_service.get_pregenerated_status',
                  return_value={'status': 'succeeded'}), \
            patch('web.reports.report_service.request_pregenerated_refresh') as refresh:
        return client.get(path), refresh


@pytest.mark.parametrize('path', [
    '/reports/demo/priv/',
    '/reports/demo/priv/1',
    '/reports/demo/priv/status',
    '/reports/demo/priv/file/csv',
    '/reports/demo/priv/download.csv',
])
def test_sysadmin_only_report_is_404_for_everyone_else(client, path):
    response, refresh = _routes(client, PRIVATE, False, path)
    assert response.status_code == 404
    refresh.assert_not_called()


def test_sysadmin_gets_status_of_sysadmin_only_report(client):
    response, _ = _routes(client, PRIVATE, True, '/reports/demo/priv/status')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'succeeded'


def test_public_report_does_not_need_the_sysadmin_check(client):
    response, _ = _routes(client, dict(PUBLIC, pregenerated=1), False, '/reports/demo/pub/status')
    assert response.status_code == 200


def test_file_route_sends_private_file_to_sysadmin(client, tmp_path, monkeypatch):
    monkeypatch.setattr(sr, 'ARTIFACT_DIR', str(tmp_path))
    name = rs.private_artifact_base(7, 'priv') + '_20261013_020000.csv'
    (tmp_path / name).write_text('a\n1\n')
    status = {'status': 'succeeded', 'artifact_path_csv': name}
    with patch('web.reports.report_service.get_project_id', return_value=7), \
            patch('web.reports.report_service.get_project_report', return_value=PRIVATE), \
            patch('web.reports.sysadmin_allowed', return_value=True), \
            patch('web.reports.report_service.get_pregenerated_status', return_value=status):
        response = client.get('/reports/demo/priv/file/csv')
        missing = client.get('/reports/demo/priv/file/xlsx')
        bad = client.get('/reports/demo/priv/file/exe')
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'a\n1\n'
    assert name in response.headers['Content-Disposition']
    assert missing.status_code == 404
    assert bad.status_code == 404


# ---- materializer ---------------------------------------------------------

def test_materializer_writes_sysadmin_only_files_outside_static(tmp_path, monkeypatch):
    import scripts.materialize_reports as m

    private_dir = tmp_path / 'private'
    monkeypatch.setattr(sr, 'ARTIFACT_DIR', str(private_dir))
    monkeypatch.chdir(tmp_path)
    public_dir = tmp_path / 'static' / 'reports'
    public_dir.mkdir(parents=True)
    # Left by a run from before the report was restricted, plus a neighbour's file.
    (public_dir / 'report_priv_20261001_020000.csv').write_text('old\n')
    (public_dir / 'report_priv_extra_20261001_020000.csv').write_text('keep\n')

    statuses = []
    with patch.object(m.report_service, 'get_project_report', return_value=dict(PRIVATE, query='SELECT 1')), \
            patch.object(m.report_service, 'get_report_last_updated', return_value='2026-10-13'), \
            patch.object(m, '_ensure_table'), \
            patch.object(m, 'run_query', return_value=[{'a': 1}, {'a': 2}]), \
            patch.object(m, '_set_status', side_effect=lambda *a, **kw: statuses.append(kw)):
        m._materialize_one(7, 'priv')

    done = statuses[-1]
    assert done['status'] == 'succeeded' and done['row_count'] == 2
    assert not done['artifact_path_csv'].startswith('reports/')
    assert sorted(os.listdir(private_dir)) == sorted([done['artifact_path_csv'], done['artifact_path_xlsx']])
    assert sorted(os.listdir(public_dir)) == ['report_priv_extra_20261001_020000.csv']
    assert rs.artifact_file(PRIVATE, done, 'csv') == (
        'private', os.path.realpath(private_dir / done['artifact_path_csv']))
