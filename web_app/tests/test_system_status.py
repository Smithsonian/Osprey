"""system_status collectors: isolation between sections and log tailing."""

from unittest.mock import patch

from osprey.services import system_status


def test_failed_section_does_not_break_others():
    with patch.object(system_status, 'db_info', side_effect=RuntimeError('db down')):
        status = system_status.collect()
    assert status['db'] == {'ok': False, 'error': 'RuntimeError: db down'}
    assert status['app']['ok'] is True


def test_tail_errors_keeps_only_error_lines_newest_first(tmp_path):
    log = tmp_path / 'ospreyapp.log'
    log.write_text('INFO | a\nERROR | first\nWARNING | b\nCRITICAL | second\n')
    result = system_status._tail_errors(str(log))
    assert result['lines'] == ['CRITICAL | second', 'ERROR | first']


def test_tail_errors_missing_file(tmp_path):
    result = system_status._tail_errors(str(tmp_path / 'nope.log'))
    assert result == {'path': str(tmp_path / 'nope.log'), 'exists': False, 'lines': []}


def test_reports_missing_table_is_not_an_error():
    err = Exception('no table')
    err.errno = system_status.ER_NO_SUCH_TABLE
    with patch.object(system_status.db, 'run_query', side_effect=err):
        assert system_status.reports_info() == {'table_present': False}
