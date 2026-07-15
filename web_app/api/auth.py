"""API authentication helpers."""

import uuid

from flask import jsonify, request
from flask_login import current_user

from logger import api_logger as logger
from osprey.db import query_database_insert, run_query
from osprey.files import check_file_id


def validate_api_key(api_key=None, url=None, params=None):
    if api_key is None:
        return False, False
    try:
        uuid.UUID(api_key)
    except ValueError:
        return False, False
    query = "SELECT api_key, is_admin from api_keys WHERE api_key = %(api_key)s and is_active = 1"
    parameters = {'api_key': api_key}
    data = run_query(query, parameters=parameters, return_val=True)
    if len(data) == 1:
        if data[0]['api_key'] == api_key:
            if data[0]['is_admin'] != 1:
                usage_query = (
                    "INSERT INTO api_keys_usage (api_key, valid, url, params) "
                    "VALUES (%(api_key)s, 1, %(url)s, %(params)s)"
                )
                query_database_insert(
                    usage_query,
                    {'api_key': api_key, 'url': url, 'params': params},
                )
            return True, data[0]['is_admin'] == 1
        usage_query = (
            "INSERT INTO api_keys_usage (api_key, valid, url, params) "
            "VALUES (%(api_key)s, 0, %(url)s, %(params)s)"
        )
        query_database_insert(
            usage_query,
            {'api_key': api_key, 'url': url, 'params': params},
        )
        return False, False
    usage_query = (
        "INSERT INTO api_keys_usage (api_key, valid, url, params) "
        "VALUES (%(api_key)s, 0, %(url)s, %(params)s)"
    )
    query_database_insert(
        usage_query,
        {'api_key': api_key, 'url': url, 'params': params},
    )
    return False, False


def require_session_or_api_key(url=None, params=None):
    """
    Allow the request if the user has a Flask-Login session or a valid API key.

    Returns None on success, or a (response, status) tuple on failure.
    """
    if current_user.is_authenticated:
        return None

    api_key = request.values.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'Authentication required'}), 401

    valid_api_key, _is_admin = validate_api_key(api_key, url=url, params=params)
    if not valid_api_key:
        return jsonify({'error': 'Forbidden'}), 403
    return None
