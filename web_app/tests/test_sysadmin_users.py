"""sysadmin_users.deactivate_user/reactivate_user: guards and the UPDATE each issues."""

from unittest.mock import patch

from osprey.services import sysadmin_users as su


def _run(row):
    calls = []

    def rq(query, params=None, return_val=True):
        calls.append((query, params))
        return ([row] if row else []) if query.startswith('SELECT') else True

    with patch.object(su, 'run_query', side_effect=rq):
        result = su.deactivate_user(7, 'alice')
    return result, calls


def _run_reactivate(row):
    calls = []

    def rq(query, params=None, return_val=True):
        calls.append((query, params))
        return ([row] if row else []) if query.startswith('SELECT') else True

    with patch.object(su, 'run_query', side_effect=rq):
        result = su.reactivate_user(7)
    return result, calls


def test_deactivates_active_user():
    result, calls = _run({'user_id': 7, 'username': 'bob', 'user_active': 1})
    assert result == (su.OK, 'bob')
    update = calls[1]
    assert update[0] == "UPDATE users SET user_active = 0 WHERE user_id = %(uid)s AND user_active = 1"
    assert update[1] == {'uid': 7}


def test_refuses_self():
    result, calls = _run({'user_id': 7, 'username': 'alice', 'user_active': 1})
    assert result == (su.SELF, 'alice') and len(calls) == 1


def test_already_inactive_no_update():
    result, calls = _run({'user_id': 7, 'username': 'bob', 'user_active': 0})
    assert result == (su.ALREADY_INACTIVE, 'bob') and len(calls) == 1


def test_not_found():
    result, calls = _run(None)
    assert result == (su.NOT_FOUND, None) and len(calls) == 1


def test_reactivates_inactive_user():
    result, calls = _run_reactivate({'user_id': 7, 'username': 'bob', 'user_active': 0})
    assert result == (su.OK, 'bob')
    update = calls[1]
    assert update[0] == "UPDATE users SET user_active = 1 WHERE user_id = %(uid)s AND user_active = 0"
    assert update[1] == {'uid': 7}


def test_already_active_no_update():
    result, calls = _run_reactivate({'user_id': 7, 'username': 'bob', 'user_active': 1})
    assert result == (su.ALREADY_ACTIVE, 'bob') and len(calls) == 1


def test_reactivate_not_found():
    result, calls = _run_reactivate(None)
    assert result == (su.NOT_FOUND, None) and len(calls) == 1
