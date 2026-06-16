"""API authentication helpers."""

import uuid

from logger import logger
from osprey.db import query_database_insert, run_query
from osprey.files import check_file_id


def validate_api_key(api_key=None, url=None, params=None):
    logger.info("api_key: {}".format(api_key))
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
