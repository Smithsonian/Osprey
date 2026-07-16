"""Unit tests for projects.img2obj SQL helpers."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

if 'osprey.db' not in sys.modules:
    _db = types.ModuleType('osprey.db')
    _db.run_query = MagicMock()
    _db.query_database_insert = MagicMock()
    sys.modules['osprey.db'] = _db

from osprey.services.img2obj import (  # noqa: E402
    get_project_img2obj_sql,
    object_count_expression,
    qualify_img2obj_sql,
)


def test_qualify_file_name():
    assert qualify_img2obj_sql('file_name') == 'f.file_name'


def test_qualify_substring_index():
    expr = "SUBSTRING_INDEX(file_name, '_', 1)"
    assert qualify_img2obj_sql(expr) == "SUBSTRING_INDEX(f.file_name, '_', 1)"


def test_qualify_rejects_unsafe_sql():
    with pytest.raises(ValueError):
        qualify_img2obj_sql('file_name; DROP TABLE files')


@patch('osprey.services.img2obj.run_query')
def test_get_project_img2obj_sql_uses_db_value(mock_run_query):
    mock_run_query.return_value = [
        {'img2obj': "SUBSTRING_INDEX(file_name, '_', 1)"},
    ]
    assert get_project_img2obj_sql(42) == "SUBSTRING_INDEX(f.file_name, '_', 1)"
    mock_run_query.assert_called_once()


@patch('osprey.services.img2obj.run_query')
def test_get_project_img2obj_sql_defaults_to_file_name(mock_run_query):
    mock_run_query.return_value = [{'img2obj': None}]
    assert get_project_img2obj_sql(7) == 'f.file_name'


@patch('osprey.services.img2obj.get_project_img2obj_sql')
def test_object_count_expression(mock_get_sql):
    mock_get_sql.return_value = 'f.file_name'
    assert object_count_expression(1) == 'COUNT(DISTINCT f.file_name)'
