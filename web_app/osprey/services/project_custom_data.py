"""Project custom data: per-project lists of values for each data type.

Tables in db/project_custom_data.sql. Each data type belongs to one project
(key: project_id + type_id) and is defined by hand; values are
added/removed on /sysadmin/data/. Removal is a soft delete (removed_at/by),
so the rows double as an audit trail; re-adding a removed value restores it.
Report queries read the project_custom_data view (current values only).
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation

from osprey.db import query_database_insert, run_query

TYPE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
MAX_VALUE_LEN = 255
MAX_VALUES_PER_SUBMIT = 500


class DataEntryError(ValueError):
    """A submitted value that does not fit its data type."""


def tables_exist() -> bool:
    rows = run_query(
        "SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME IN ('project_custom_types', 'project_custom_values')",
        log_vals=False,
    )
    return int(rows[0]['n']) == 2


def list_projects() -> list[dict]:
    """Projects that have at least one data type (others have nothing to
    enter), active first, with their type and current-value counts."""
    return run_query(
        "SELECT p.project_id, p.project_title, p.project_alias, p.project_status, "
        "  COUNT(DISTINCT t.type_id) AS n_types, COUNT(v.value_id) AS n_values "
        "FROM projects p "
        "JOIN project_custom_types t ON t.project_id = p.project_id "
        "LEFT JOIN project_custom_values v ON v.project_id = t.project_id "
        "  AND v.type_id = t.type_id AND v.removed_at IS NULL "
        "GROUP BY p.project_id, p.project_title, p.project_alias, p.project_status "
        "ORDER BY p.project_status = 'Completed', p.project_title",
        log_vals=False,
    )


def get_project(project_id: int) -> dict | None:
    rows = run_query(
        "SELECT project_id, project_title, project_alias, project_status FROM projects "
        "WHERE project_id = %(pid)s", {'pid': project_id})
    return rows[0] if rows else None


def list_types(project_id: int) -> list[dict]:
    """This project's data types, with their number of current values."""
    return run_query(
        "SELECT t.type_id, t.label, t.description, t.value_type, COUNT(v.value_id) AS n_values "
        "FROM project_custom_types t LEFT JOIN project_custom_values v "
        "  ON v.project_id = t.project_id AND v.type_id = t.type_id AND v.removed_at IS NULL "
        "WHERE t.project_id = %(pid)s "
        "GROUP BY t.type_id, t.label, t.description, t.value_type, t.sort_order "
        "ORDER BY t.sort_order, t.label",
        {'pid': project_id},
    )


def get_type(project_id: int, type_id: str) -> dict | None:
    """The project's own type; None for another project's type_id."""
    if not TYPE_ID_RE.match(type_id or ''):
        return None
    rows = run_query(
        "SELECT type_id, label, description, value_type FROM project_custom_types "
        "WHERE project_id = %(pid)s AND type_id = %(tid)s", {'pid': project_id, 'tid': type_id})
    return rows[0] if rows else None


def list_values(project_id: int, type_id: str) -> dict:
    """Current values and removed ones (history) for a project and type."""
    rows = run_query(
        "SELECT value_id, value, note, added_by, added_at, removed_by, removed_at "
        "FROM project_custom_values WHERE project_id = %(pid)s AND type_id = %(tid)s "
        "ORDER BY value",
        {'pid': project_id, 'tid': type_id},
    )
    return {
        'current': [r for r in rows if r['removed_at'] is None],
        'removed': sorted((r for r in rows if r['removed_at'] is not None),
                          key=lambda r: r['removed_at'], reverse=True),
    }


def parse_values(raw: str, value_type: str) -> list[str]:
    """Split the textarea (one value per line), trim, de-duplicate, validate.

    Numbers are stored in a canonical form (Decimal, no exponent) and dates
    as YYYY-MM-DD, so the same value always matches the unique key.
    """
    out = []
    for line in (raw or '').splitlines():
        v = line.strip()
        if not v:
            continue
        if len(v) > MAX_VALUE_LEN:
            raise DataEntryError("'{}…' is longer than {} characters".format(v[:30], MAX_VALUE_LEN))
        if value_type == 'number':
            try:
                d = Decimal(v.replace(',', ''))
            except InvalidOperation:
                raise DataEntryError("'{}' is not a number".format(v)) from None
            if not d.is_finite():
                raise DataEntryError("'{}' is not a number".format(v))
            v = format(d.normalize(), 'f')
        elif value_type == 'date':
            try:
                v = datetime.date.fromisoformat(v).isoformat()
            except ValueError:
                raise DataEntryError("'{}' is not a date (use YYYY-MM-DD)".format(v)) from None
        if v not in out:
            out.append(v)
    if not out:
        raise DataEntryError("no values entered")
    if len(out) > MAX_VALUES_PER_SUBMIT:
        raise DataEntryError("at most {} values per save".format(MAX_VALUES_PER_SUBMIT))
    return out


def add_values(project_id: int, type_id: str, values: list[str], note: str | None, username: str) -> int:
    """Add values; a previously removed value is restored. Returns how many were saved.

    Values already current are left untouched (their original added_by stays).
    """
    saved = 0
    for v in values:
        query_database_insert(
            "INSERT INTO project_custom_values (project_id, type_id, value, note, added_by) "
            "VALUES (%(pid)s, %(tid)s, %(v)s, %(note)s, %(user)s) "
            "ON DUPLICATE KEY UPDATE "
            "  note = IF(removed_at IS NULL, note, VALUES(note)), "
            "  added_by = IF(removed_at IS NULL, added_by, VALUES(added_by)), "
            "  added_at = IF(removed_at IS NULL, added_at, CURRENT_TIMESTAMP), "
            "  removed_by = NULL, removed_at = NULL",
            {'pid': project_id, 'tid': type_id, 'v': v, 'note': note or None, 'user': username},
        )
        saved += 1
    return saved


def remove_value(project_id: int, type_id: str, value_id: int, username: str) -> bool:
    """Soft-delete one current value; the project/type check stops a crafted id
    from touching another project's data. True if a row was removed."""
    rows = run_query(
        "SELECT value FROM project_custom_values WHERE value_id = %(vid)s AND project_id = %(pid)s "
        "AND type_id = %(tid)s AND removed_at IS NULL",
        {'vid': value_id, 'pid': project_id, 'tid': type_id},
    )
    if not rows:
        return False
    run_query(
        "UPDATE project_custom_values SET removed_by = %(user)s, removed_at = CURRENT_TIMESTAMP "
        "WHERE value_id = %(vid)s AND project_id = %(pid)s AND type_id = %(tid)s AND removed_at IS NULL",
        {'user': username, 'vid': value_id, 'pid': project_id, 'tid': type_id},
        return_val=False,
    )
    return True
