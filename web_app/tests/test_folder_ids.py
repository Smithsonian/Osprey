"""Unit tests for folder ID listing helper."""

from unittest.mock import MagicMock, patch

from osprey.services.folders import list_folder_ids_for_project


@patch('osprey.services.folders.run_query')
def test_list_folder_ids_all_folders(mock_run_query):
    mock_run_query.return_value = [{'folder_id': 1}, {'folder_id': 2}]
    rows = list_folder_ids_for_project(10, transcription=0, status=None)
    assert rows == [{'folder_id': 1}, {'folder_id': 2}]
    query, params = mock_run_query.call_args[0]
    assert 'FROM folders' in query
    assert 'AND status' not in query
    assert params == {'project_id': 10}


@patch('osprey.services.folders.run_query')
def test_list_folder_ids_with_status_filter(mock_run_query):
    mock_run_query.return_value = [{'folder_id': 3}]
    rows = list_folder_ids_for_project(10, transcription=0, status=0)
    assert rows == [{'folder_id': 3}]
    query, params = mock_run_query.call_args[0]
    assert 'AND status = %(status)s' in query
    assert params == {'project_id': 10, 'status': 0}


@patch('osprey.services.folders.run_query')
def test_list_folder_ids_transcription_table(mock_run_query):
    mock_run_query.return_value = []
    list_folder_ids_for_project(22, transcription=1, status=1)
    query, params = mock_run_query.call_args[0]
    assert 'FROM transcription_folders' in query
    assert 'folder_transcription_id AS folder_id' in query
    assert params == {'project_id': 22, 'status': 1}
