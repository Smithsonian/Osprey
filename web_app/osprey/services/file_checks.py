"""Parameterized file-check helpers (no DB-stored SQL execution)."""

from __future__ import annotations

import re

from logger import api_logger as logger
from osprey.db import run_query

# Projects that use ArchivesSpace RefID salvage after a failed filename check.
_JPCA_PROJECT_IDS = {"220", "248"}

# Statement keywords / comment markers that must never appear in scalar expressions.
_FORBIDDEN_SQL = re.compile(
    r"(;|--|/\*|\*/|\b(select|insert|update|delete|drop|alter|truncate|create|replace|"
    r"grant|revoke|exec|execute|call|union|into|outfile|load_file|benchmark|"
    r"sleep|information_schema)\b)",
    re.IGNORECASE,
)


def assert_safe_sql_expression(expr: str) -> str:
    """
    Validate a scalar SQL expression fragment before interpolating into a template.
    Fails closed: raises ValueError if the expression is empty or unsafe.
    """
    if expr is None:
        raise ValueError("SQL expression is empty")
    cleaned = str(expr).replace("\\", "").strip()
    if not cleaned:
        raise ValueError("SQL expression is empty")
    if _FORBIDDEN_SQL.search(cleaned):
        raise ValueError("SQL expression contains forbidden tokens")
    if cleaned.count("(") != cleaned.count(")"):
        raise ValueError("SQL expression has unbalanced parentheses")
    return cleaned


def filename_check_enabled(project_id) -> bool:
    """Return True when the project has the filename check enabled in settings."""
    rows = run_query(
        (
            "SELECT 1 AS ok FROM projects_settings "
            "WHERE project_id = %(project_id)s "
            "  AND project_setting = 'project_checks' "
            "  AND settings_value = 'filename' "
            "LIMIT 1"
        ),
        {'project_id': project_id},
    )
    return len(rows) == 1


def run_filename_check(file_id, project_id=None) -> dict:
    """
    Fixed parameterized filename check.

    Returns a row dict with keys: result (0=pass, 1=fail), info, refid.
    RefID is the underscore-separated prefix of file_name.

    For JPCA projects (220, 248): fail unless the RefID is already in jpc_aspace_data
    so the existing ArchivesSpace salvage path can still run.
    For other projects: fail only on missing/malformed names (no underscore).
    """
    is_jpca = project_id is not None and str(project_id) in _JPCA_PROJECT_IDS
    if is_jpca:
        query = (
            "SELECT "
            "  CASE "
            "    WHEN f.file_name IS NULL OR TRIM(f.file_name) = '' THEN 1 "
            "    WHEN j.refid IS NULL THEN 1 "
            "    ELSE 0 "
            "  END AS result, "
            "  CASE "
            "    WHEN f.file_name IS NULL OR TRIM(f.file_name) = '' THEN 'Missing file name' "
            "    WHEN j.refid IS NULL THEN SUBSTRING_INDEX(f.file_name, '_', 1) "
            "    ELSE j.refid "
            "  END AS info, "
            "  SUBSTRING_INDEX(f.file_name, '_', 1) AS refid "
            "FROM files f "
            "LEFT JOIN jpc_aspace_data j "
            "  ON j.refid = SUBSTRING_INDEX(f.file_name, '_', 1) "
            "WHERE f.file_id = %(file_id)s"
        )
    else:
        query = (
            "SELECT "
            "  CASE "
            "    WHEN f.file_name IS NULL OR TRIM(f.file_name) = '' THEN 1 "
            "    WHEN INSTR(f.file_name, '_') = 0 THEN 1 "
            "    ELSE 0 "
            "  END AS result, "
            "  CASE "
            "    WHEN f.file_name IS NULL OR TRIM(f.file_name) = '' THEN 'Missing file name' "
            "    WHEN INSTR(f.file_name, '_') = 0 THEN 'Filename missing expected underscore separator' "
            "    ELSE SUBSTRING_INDEX(f.file_name, '_', 1) "
            "  END AS info, "
            "  SUBSTRING_INDEX(COALESCE(f.file_name, ''), '_', 1) AS refid "
            "FROM files f "
            "WHERE f.file_id = %(file_id)s"
        )
    rows = run_query(query, {'file_id': file_id})
    if not rows:
        logger.warning("filename check: file_id not found | file_id=%s", file_id)
        return {'result': 1, 'info': 'File not found', 'refid': None}
    return rows[0]
