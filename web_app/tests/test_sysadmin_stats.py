"""sysadmin_stats jobs: report_id mapping, run_job writes, queue and runner wiring."""

import datetime
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from osprey.services import sysadmin_stats as st

RUN_AT = datetime.datetime(2026, 10, 13, 2, 30)
ROOT = Path(__file__).resolve().parent.parent


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_report_id_round_trip():
    assert st.report_id_for('files_exif') == 'stat:files_exif'
    assert st.job_id_from_report('stat:files_exif') == 'files_exif'
    assert st.job_id_from_report('stat:unknown') is None
    assert st.job_id_from_report('transcription_profile') is None


def test_every_job_declares_stats_and_selects_project_id():
    for job_id, job in st.STAT_JOBS.items():
        assert job['stats'], job_id
        assert 'project_id' in job['sql'], job_id
        for stat_id in job['stats']:
            assert stat_id in job['sql'] and len(stat_id) <= 64, (job_id, stat_id)


def _run(results):
    calls = []

    def rq(query, params=None, return_val=True, log_vals=True):
        calls.append((query, params))
        if query.startswith('SELECT NOW()'):
            return [{'now': RUN_AT}]
        if query == st.STAT_JOBS['files_exif']['sql']:
            return results
        return True

    with patch.object(st, 'run_query', side_effect=rq), patch.object(st, 'executemany') as em:
        n = st.run_job('files_exif')
    return n, calls, em


def test_run_job_writes_one_row_per_stat_and_project():
    n, calls, em = _run([{'project_id': 10, 'files_exif_rows': 100, 'files_exif_files': 4},
                         {'project_id': 0, 'files_exif_rows': 7, 'files_exif_files': None}])
    assert n == 4
    assert sorted(em.call_args[0][1]) == sorted([
        ('files_exif_rows', 10, 100, RUN_AT), ('files_exif_files', 10, 4, RUN_AT),
        ('files_exif_rows', 0, 7, RUN_AT), ('files_exif_files', 0, 0, RUN_AT)])
    delete = [c for c in calls if c[0].startswith('DELETE FROM sysadmin_stats')]
    assert len(delete) == 1
    # Prune is scoped to this job's stats and this run.
    assert set(delete[0][1].values()) == {'files_exif_rows', 'files_exif_files', RUN_AT}


def test_run_job_with_no_results_only_prunes():
    n, calls, em = _run([])
    assert n == 0
    em.assert_not_called()
    assert any(c[0].startswith('DELETE FROM sysadmin_stats') for c in calls)


def test_run_job_rejects_query_missing_a_stat_column():
    with pytest.raises(KeyError):
        _run([{'project_id': 10, 'files_exif_rows': 1}])


def test_queue_adds_stat_jobs_last():
    q = _load_script('queue_nightly_reports')
    with patch.object(q, 'list_pregenerated_reports', return_value=[{'project_id': 1, 'report_id': 'r'}]), \
            patch.object(q, 'list_transcription_profile_jobs', return_value=[]), \
            patch.object(q.materializations, 'request_refresh', return_value=True) as req:
        assert q.queue_all() == 1 + len(st.STAT_JOBS)
    queued = [c.args[:2] for c in req.call_args_list]
    assert queued[0] == (1, 'r')
    assert queued[1:] == [(0, 'stat:' + j) for j in st.STAT_JOBS]


def test_runner_dispatches_stat_jobs_and_records_status():
    m = _load_script('materialize_reports')
    with patch.object(m.sysadmin_stats, 'run_job', return_value=6) as run, \
            patch.object(m, '_set_status') as status:
        m._materialize_one(0, 'stat:files_exif')
    run.assert_called_once_with('files_exif')
    assert status.call_args.kwargs['status'] == 'succeeded'
    assert status.call_args.kwargs['row_count'] == 6


def test_runner_records_stat_failure():
    m = _load_script('materialize_reports')
    with patch.object(m.sysadmin_stats, 'run_job', side_effect=RuntimeError('boom')), \
            patch.object(m, '_set_status') as status:
        with pytest.raises(RuntimeError):
            m._materialize_one(0, 'stat:files_exif')
    assert status.call_args.kwargs['status'] == 'failed'
    assert status.call_args.kwargs['error_message'] == 'boom'
