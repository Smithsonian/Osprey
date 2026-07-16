"""Unit tests for pregenerated report preview helpers."""

import sys
import types
from unittest.mock import MagicMock, patch

import pandas as pd

# Lightweight module stubs so reports.py imports without full app settings.
if 'logger' not in sys.modules:
    _logger_mod = types.ModuleType('logger')
    _logger_mod.logger = MagicMock()
    sys.modules['logger'] = _logger_mod

if 'osprey.db' not in sys.modules:
    _db = types.ModuleType('osprey.db')
    _db.run_query = MagicMock(return_value=[])
    _db.query_database_insert = MagicMock()
    sys.modules['osprey.db'] = _db

from osprey.services import reports as report_service  # noqa: E402


def test_get_pregenerated_preview_returns_none_when_not_succeeded():
    report = {'project_id': 1, 'report_id': 'big'}
    with patch.object(
        report_service,
        'get_pregenerated_status',
        return_value={
            'status': 'queued',
            'materialized_table_name': 'rptmat_p1_big',
            'last_succeeded_at': None,
        },
    ):
        assert report_service.get_pregenerated_preview(report) is None


def test_get_pregenerated_preview_allows_prior_success_while_queued():
    report = {'project_id': 1, 'report_id': 'big'}
    rows = [{'a': 1}]
    with patch.object(
        report_service,
        'get_pregenerated_status',
        return_value={
            'status': 'queued',
            'materialized_table_name': 'rptmat_p1_report_big',
            'last_succeeded_at': '2026-01-01 00:00:00',
        },
    ), patch.object(report_service, 'run_query', return_value=rows):
        df = report_service.get_pregenerated_preview(report)
        assert list(df['a']) == [1]


def test_get_pregenerated_preview_rejects_unsafe_table_name():
    report = {'project_id': 1, 'report_id': 'big'}
    with patch.object(
        report_service,
        'get_pregenerated_status',
        return_value={
            'status': 'succeeded',
            'materialized_table_name': 'rptmat`; DROP TABLE users;--',
        },
    ):
        assert report_service.get_pregenerated_preview(report) is None


def test_get_pregenerated_preview_limits_rows():
    report = {'project_id': 1, 'report_id': 'big'}
    rows = [{'a': 1}, {'a': 2}]
    with patch.object(
        report_service,
        'get_pregenerated_status',
        return_value={
            'status': 'succeeded',
            'materialized_table_name': 'rptmat_p1_report_big',
        },
    ), patch.object(report_service, 'run_query', return_value=rows) as mock_run:
        df = report_service.get_pregenerated_preview(report, limit=20)
        assert isinstance(df, pd.DataFrame)
        assert list(df['a']) == [1, 2]
        sql, params = mock_run.call_args[0][0], mock_run.call_args[0][1]
        assert 'LIMIT %(limit)s' in sql
        assert '`rptmat_p1_report_big`' in sql
        assert params == {'limit': 20}


def test_get_pregenerated_preview_returns_none_on_query_error():
    report = {'project_id': 1, 'report_id': 'big'}
    with patch.object(
        report_service,
        'get_pregenerated_status',
        return_value={
            'status': 'succeeded',
            'materialized_table_name': 'rptmat_p1_report_big',
        },
    ), patch.object(report_service, 'run_query', return_value=False):
        assert report_service.get_pregenerated_preview(report) is None
