"""sysadmin_qc: project picker, per-project QC settings row, and setting qc_method."""

from unittest.mock import patch

import pytest

from osprey.services import sysadmin_qc as sq


def test_list_projects_orders_completed_last():
    with patch.object(sq.db, 'run_query', return_value=[]) as rq:
        sq.list_projects()
    query = rq.call_args[0][0]
    assert 'FROM projects' in query and "project_status = 'Completed'" in query


def test_get_project_returns_none_when_missing():
    with patch.object(sq.db, 'run_query', return_value=[]) as rq:
        assert sq.get_project(99) is None
    assert rq.call_args[0][1] == {'pid': 99}


def test_get_project_returns_row():
    row = {'project_id': 12, 'project_alias': 'bot', 'project_title': 'Botany',
           'project_status': 'Ongoing', 'transcription': 0}
    with patch.object(sq.db, 'run_query', return_value=[row]):
        assert sq.get_project(12) == row


def test_get_settings_reads_qc_settings_for_regular_project():
    project = {'project_id': 12, 'transcription': 0}
    with patch.object(sq.db, 'run_query', return_value=[{'qc_level': 'Normal'}]) as rq:
        out = sq.get_settings(project)
    query = rq.call_args[0][0]
    assert 'FROM qc_settings' in query and 'transcription_qc_settings' not in query
    assert rq.call_args[0][1] == {'pid': 12}
    assert out == {'qc_level': 'Normal'}


def test_get_settings_reads_transcription_qc_settings_for_transcription_project():
    project = {'project_id': 7, 'transcription': 1}
    with patch.object(sq.db, 'run_query', return_value=[{'qc_level': 'Tightened'}]) as rq:
        out = sq.get_settings(project)
    query = rq.call_args[0][0]
    assert 'FROM transcription_qc_settings' in query
    assert out == {'qc_level': 'Tightened'}


def test_get_settings_returns_none_when_no_row_yet():
    project = {'project_id': 12, 'transcription': 0}
    with patch.object(sq.db, 'run_query', return_value=[]):
        assert sq.get_settings(project) is None


@pytest.mark.parametrize('transcription, table', [(0, 'UPDATE qc_settings '), (1, 'UPDATE transcription_qc_settings ')])
def test_set_method_updates_the_projects_settings_table(transcription, table):
    with patch.object(sq.db, 'query_database_insert', return_value=True) as qi:
        sq.set_method({'project_id': 12, 'transcription': transcription}, 'cumulative')
    assert qi.call_args[0][0].startswith(table)
    assert qi.call_args[0][1] == {'method': 'cumulative', 'pid': 12}


def test_set_method_rejects_unknown_method():
    with patch.object(sq.db, 'query_database_insert') as qi, pytest.raises(ValueError):
        sq.set_method({'project_id': 12, 'transcription': 0}, 'bogus')
    qi.assert_not_called()


def test_locks_reads_all_three_lock_kinds_oldest_first():
    from datetime import datetime
    folder = {'kind': 'folder', 'updated_at': datetime(2026, 3, 1)}
    tfolder = {'kind': 'transcription_folder', 'updated_at': datetime(2026, 1, 1)}
    text = {'kind': 'text', 'updated_at': datetime(2026, 2, 1)}
    with patch.object(sq.db, 'run_query', side_effect=[[folder], [tfolder], [text]]) as rq:
        out = sq.locks()
    assert [r['kind'] for r in out] == ['transcription_folder', 'text', 'folder']
    queries = [c[0][0] for c in rq.call_args_list]
    assert 'qc_folders q JOIN folders f ON f.folder_id = q.folder_id' in queries[0]
    assert 'f.folder_transcription_id = q.folder_uid' in queries[1]
    assert 'FROM transcription_qc_folders q' in queries[2]
    # Same lock rule as the /qc "Folders with QC in Progress" list.
    assert all('q.qc_by IS NOT NULL' in q and 'NOT IN (0, 1)' in q for q in queries)
