"""validate_api_key: active, expired and unknown keys."""

from unittest.mock import patch

import pytest

pytest.importorskip('flask')

from api import auth

KEY = '11111111-2222-3333-4444-555555556789'


def _validate(rows):
    with patch.object(auth, 'run_query', return_value=rows) as rq, \
            patch.object(auth, 'query_database_insert') as ins:
        result = auth.validate_api_key(KEY, url='/api/x', params='p')
    return result, rq, ins


def test_query_checks_expiry_in_sql():
    _, rq, _ = _validate([])
    assert 'expires_on > NOW()' in rq.call_args[0][0]


def test_active_unexpired_key_is_valid():
    result, _, ins = _validate([{'api_key': KEY, 'is_admin': 0, 'not_expired': 1}])
    assert result == (True, False)
    assert ins.call_args[0][1]['api_key'] == KEY
    assert ', 1, ' in ins.call_args[0][0]  # logged as a valid use


def test_admin_unexpired_key_is_valid_and_not_logged():
    result, _, ins = _validate([{'api_key': KEY, 'is_admin': 1, 'not_expired': 1}])
    assert result == (True, True)
    ins.assert_not_called()


@pytest.mark.parametrize('is_admin', [0, 1])
def test_expired_key_is_rejected_and_logged_invalid(is_admin):
    result, _, ins = _validate([{'api_key': KEY, 'is_admin': is_admin, 'not_expired': 0}])
    assert result == (False, False)
    ins.assert_called_once()
    assert ', 0, ' in ins.call_args[0][0]


def test_unknown_key_is_rejected():
    result, _, ins = _validate([])
    assert result == (False, False)
    ins.assert_called_once()


def test_malformed_key_never_queries():
    with patch.object(auth, 'run_query') as rq:
        assert auth.validate_api_key('not-a-uuid') == (False, False)
    rq.assert_not_called()
