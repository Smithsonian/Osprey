"""Per-project file_name → object identity from projects.img2obj."""

from __future__ import annotations

import re

from osprey.db import run_query
from osprey.services.file_checks import assert_safe_sql_expression

_FILE_NAME_TOKEN = re.compile(r'\bfile_name\b', re.IGNORECASE)
_DEFAULT_IMG2OBJ = 'file_name'


def qualify_img2obj_sql(expr: str, *, table_alias: str = 'f') -> str:
    """Validate img2obj and qualify bare file_name references with a table alias.

    Examples (table_alias='f'):
      file_name -> f.file_name
      SUBSTRING_INDEX(file_name, '_', 1) -> SUBSTRING_INDEX(f.file_name, '_', 1)
    """
    cleaned = assert_safe_sql_expression(expr)
    if cleaned.lower() == 'file_name':
        return f'{table_alias}.file_name'
    return _FILE_NAME_TOKEN.sub(f'{table_alias}.file_name', cleaned)


def get_project_img2obj_sql(project_id, *, table_alias: str = 'f') -> str:
    """Load and qualify projects.img2obj for use in a files query."""
    rows = run_query(
        'SELECT img2obj FROM projects WHERE project_id = %(project_id)s',
        {'project_id': project_id},
    )
    if not rows:
        raise ValueError(f'Project not found: {project_id}')
    raw = rows[0].get('img2obj')
    expr = raw if raw and str(raw).strip() else _DEFAULT_IMG2OBJ
    return qualify_img2obj_sql(expr, table_alias=table_alias)


def object_count_expression(project_id, *, table_alias: str = 'f') -> str:
    """Aggregate object count aligned with img2obj (for rollups)."""
    obj_sql = get_project_img2obj_sql(project_id, table_alias=table_alias)
    return f'COUNT(DISTINCT {obj_sql})'
