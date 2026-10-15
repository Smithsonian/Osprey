"""sysadmin_qc lookups: project picker and per-project QC settings row."""

from unittest.mock import patch

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
