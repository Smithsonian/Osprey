"""API authentication helpers."""

import uuid

from logger import api_logger as logger
from osprey.db import query_database_insert, run_query


def validate_api_key(api_key=None, url=None, params=None):
    if api_key is None:
        return False, False
    try:
        uuid.UUID(api_key)
    except ValueError:
        return False, False
    # Expiry is compared in SQL so both sides use the DB session time zone
    # (osprey.db sets it per connection). api_keys.expires_on is NOT NULL.
    query = ("SELECT api_key, is_admin, expires_on > NOW() AS not_expired "
             "FROM api_keys WHERE api_key = %(api_key)s and is_active = 1")
    parameters = {'api_key': api_key}
    data = run_query(query, parameters=parameters, return_val=True)
    if len(data) == 1:
        if data[0]['api_key'] == api_key and not data[0]['not_expired']:
            # Logged as an invalid use (admin keys included) so it shows in
            # the sysadmin "invalid key attempts" list.
            logger.warning("Rejected expired api_key ...{} for {}".format(api_key[-4:], url))
            usage_query = (
                "INSERT INTO api_keys_usage (api_key, valid, url, params) "
                "VALUES (%(api_key)s, 0, %(url)s, %(params)s)"
            )
            query_database_insert(
                usage_query,
                {'api_key': api_key, 'url': url, 'params': params},
            )
            return False, False
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
