"""sysadmin_reports: query guard, artifact paths, grouping, materialize, wiring."""

import datetime
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from osprey.services import sysadmin_reports as sr

ROOT = Path(__file__).resolve().parent.parent
T1 = datetime.datetime(2026, 10, 13, 2, 0)


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('sql', [
    'SELECT 1',
    'select project_id, COUNT(*) n from folders group by project_id;',
    'WITH t AS (SELECT 1 AS x) SELECT x FROM t',
    "SELECT REPLACE(file_name, '.tif', '') AS stem, updated_at FROM files",
])
def test_check_query_accepts_read_only(sql):
    assert sr.check_query(sql).lower().startswith(('select', 'with'))


@pytest.mark.parametrize('sql', [
    '', '   ;',
    'SELECT 1; DROP TABLE users',
    'DELETE FROM files',
    'WITH t AS (SELECT 1) DELETE FROM files',
    'SELECT * FROM users INTO OUTFILE "/tmp/x"',
    'SELECT * FROM files FOR UPDATE',
    'SELECT SLEEP(100)',
    'SHOW TABLES',
])
def test_check_query_rejects(sql):
    with pytest.raises(sr.ReportError):
        sr.check_query(sql)


def test_artifact_path_stays_in_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, 'ARTIFACT_DIR', str(tmp_path))
    (tmp_path / 'r_20261013_020000.csv').write_text('a\n')
    assert sr.artifact_path('r_20261013_020000.csv') == os.path.realpath(tmp_path / 'r_20261013_020000.csv')
    assert sr.artifact_path('../settings.py') is None
    assert sr.artifact_path('/etc/passwd') is None
    assert sr.artifact_path('missing.csv') is None
    assert sr.artifact_path(None) is None


def test_get_report_rejects_bad_ids_without_query():
    with patch.object(sr, 'run_query') as rq:
        assert sr.get_report('../x') is None
        assert sr.get_report("x' OR 1=1") is None
    rq.assert_not_called()


def test_list_reports_groups_by_project_all_projects_first():
    rows = [
        {'report_id': 'a', 'project_id': None, 'project_title': None, 'project_alias': None},
        {'report_id': 'b', 'project_id': 10, 'project_title': 'P10', 'project_alias': 'p10'},
        {'report_id': 'c', 'project_id': 10, 'project_title': 'P10', 'project_alias': 'p10'},
    ]
    with patch.object(sr, 'run_query', return_value=rows) as rq:
        groups = sr.list_reports()
    assert [(g['project_id'], [r['report_id'] for r in g['reports']]) for g in groups] == [
        (None, ['a']), (10, ['b', 'c'])]
    assert rq.call_args[0][1] == {'mat_pid': 0, 'prefix': 'sysrep:'}


def test_run_live_caps_preview(monkeypatch):
    monkeypatch.setattr(sr, 'PREVIEW_ROWS', 2)
    rows = [{'x': i} for i in range(5)]
    with patch.object(sr, 'run_query', return_value=rows):
        out = sr.run_live({'query': 'SELECT x FROM t'})
    assert out['columns'] == ['x'] and len(out['rows']) == 2 and out['total'] == 5


def test_run_live_refuses_unsafe_query_before_db():
    with patch.object(sr, 'run_query') as rq, pytest.raises(sr.ReportError):
        sr.run_live({'query': 'DELETE FROM files'})
    rq.assert_not_called()


def test_live_csv():
    with patch.object(sr, 'run_query', return_value=[{'a': 1, 'b': None}, {'a': 2, 'b': 'x,y'}]):
        assert sr.live_csv({'query': 'SELECT a, b FROM t'}) == 'a,b\n1,\n2,"x,y"\n'


def test_materialize_writes_files_and_removes_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, 'ARTIFACT_DIR', str(tmp_path))
    old = tmp_path / 'rep_20200101_000000.csv'
    old.write_text('old')
    other = tmp_path / 'rep2_20200101_000000.csv'  # another report's file stays
    other.write_text('keep')
    report = {'report_id': 'rep', 'query': 'SELECT 1 AS a'}
    with patch.object(sr, 'get_report', return_value=report), \
            patch.object(sr, 'run_query', return_value=[{'a': 1}, {'a': 2}]):
        out = sr.materialize('rep')
    assert out['row_count'] == 2
    assert (tmp_path / out['csv']).read_text() == 'a\n1\n2\n'
    assert (tmp_path / out['xlsx']).is_file()
    assert not old.exists() and other.exists()
    assert oct((tmp_path / out['csv']).stat().st_mode & 0o777) == '0o640'


def test_materialize_unknown_report():
    with patch.object(sr, 'get_report', return_value=None), pytest.raises(sr.ReportError):
        sr.materialize('nope')


def test_runner_dispatches_sysadmin_reports():
    m = _load_script('materialize_reports')
    with patch.object(m.sysadmin_reports, 'materialize',
                      return_value={'row_count': 3, 'csv': 'r.csv', 'xlsx': None}) as mat, \
            patch.object(m, '_set_status') as status:
        m._materialize_one(0, 'sysrep:rep')
    mat.assert_called_once_with('rep')
    kw = status.call_args.kwargs
    assert (kw['status'], kw['row_count'], kw['artifact_path_csv']) == ('succeeded', 3, 'r.csv')


def test_runner_records_sysadmin_report_failure():
    m = _load_script('materialize_reports')
    with patch.object(m.sysadmin_reports, 'materialize', side_effect=sr.ReportError('bad')), \
            patch.object(m, '_set_status') as status, pytest.raises(sr.ReportError):
        m._materialize_one(0, 'sysrep:rep')
    assert status.call_args.kwargs['status'] == 'failed'


def test_nightly_queue_includes_pregenerated_sysadmin_reports():
    q = _load_script('queue_nightly_reports')
    with patch.object(q.sysadmin_reports, 'table_exists', return_value=True), \
            patch.object(q, 'run_query', return_value=[{'report_id': 'rep', 'title': 'Rep'}]):
        assert q.list_sysadmin_report_jobs() == [
            {'project_id': 0, 'report_id': 'sysrep:rep', 'report_title': 'Rep'}]


def test_nightly_queue_skips_when_table_missing():
    q = _load_script('queue_nightly_reports')
    with patch.object(q.sysadmin_reports, 'table_exists', return_value=False), \
            patch.object(q, 'run_query') as rq:
        assert q.list_sysadmin_report_jobs() == []
    rq.assert_not_called()
