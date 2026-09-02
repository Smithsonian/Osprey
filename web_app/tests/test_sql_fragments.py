"""Tests for the SQL-fragment sanitizer guarding DB-stored expressions
(qc_filenames, preview_filter, folder_stats fragments)."""

import pytest

from osprey.services.file_checks import assert_safe_sql_expression


def test_accepts_benign_filter_expression():
    expr = "file_name LIKE 'ab%'"
    assert assert_safe_sql_expression(expr) == expr


def test_accepts_function_expression():
    expr = "SUBSTRING_INDEX(file_name, '_', 1) = folder_name"
    assert assert_safe_sql_expression(expr) == expr


@pytest.mark.parametrize('expr', [
    "1=1; DROP TABLE files",
    "1 UNION SELECT password FROM users",
    "1=1 -- comment",
    "1 /* comment */",
    "(SELECT 1)",
    "sleep(10)",
])
def test_rejects_injection_attempts(expr):
    with pytest.raises(ValueError):
        assert_safe_sql_expression(expr)


@pytest.mark.parametrize('expr', [None, '', '   ', 'a AND (b'])
def test_rejects_empty_or_malformed(expr):
    with pytest.raises(ValueError):
        assert_safe_sql_expression(expr)
