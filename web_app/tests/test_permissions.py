"""Regression tests: permission checks must be evaluated per user / per IP.

These lock in the fix for the shared-cache bug where user_perms() served
the first visitor's admin bit to every user, and kiosk_mode() marked a
URL as kiosk for all visitors.
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip('flask_login')

from osprey.services import permissions


def _user(name):
    user = MagicMock()
    user.name = name
    return user


@patch('osprey.services.permissions.run_query')
def test_user_perms_admin_is_per_user(mock_run):
    def by_user(query, params):
        return [{'is_admin': 1 if params['user_name'] == 'alice' else 0}]

    mock_run.side_effect = by_user
    with patch('osprey.services.permissions.current_user', _user('alice')):
        assert permissions.user_perms('', user_type='admin') is True
    with patch('osprey.services.permissions.current_user', _user('bob')):
        assert permissions.user_perms('', user_type='admin') is False
    # One query per call: no result may be reused across users.
    assert mock_run.call_count == 2


@patch('osprey.services.permissions.run_query')
def test_user_perms_user_is_per_user_and_project(mock_run):
    def by_user(query, params):
        ok = params['user_name'] == 'alice' and params['project_id'] == 'p1'
        return [{'is_user': 1 if ok else 0}]

    mock_run.side_effect = by_user
    with patch('osprey.services.permissions.current_user', _user('alice')):
        assert permissions.user_perms('p1', user_type='user') is True
        assert permissions.user_perms('p2', user_type='user') is False
    with patch('osprey.services.permissions.current_user', _user('bob')):
        assert permissions.user_perms('p1', user_type='user') is False


def test_user_perms_anonymous_is_false():
    # Anonymous users have no .name attribute; must fail closed, not raise.
    with patch('osprey.services.permissions.current_user', object()):
        assert permissions.user_perms('', user_type='admin') is False


def test_kiosk_mode_is_per_client_ip():
    kiosks = ['1.2.3.4']
    kiosk_req = MagicMock(remote_addr='1.2.3.4')
    other_req = MagicMock(remote_addr='9.9.9.9')
    assert permissions.kiosk_mode(kiosk_req, kiosks) == (True, '1.2.3.4')
    # A different client hitting the same URL must not inherit kiosk mode.
    assert permissions.kiosk_mode(other_req, kiosks) == (False, '9.9.9.9')
