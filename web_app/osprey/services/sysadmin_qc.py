"""QC settings lookup for the sysadmin QC tab: one project's sampling level,
percent, and critical/major/minor thresholds.

Regular projects keep their row in qc_settings; transcription projects in
transcription_qc_settings (same columns in both — see the /qc and
/qc_transcription routes in app.py, which create the row on first visit).
Only set_method writes; a project that has never opened /qc has no row yet.

locks() lists folders held in QC across all projects, for the QC locks card.
"""

from __future__ import annotations

from osprey import db
from osprey.services import qc

SETTINGS_TABLE = {0: 'qc_settings', 1: 'transcription_qc_settings'}


def list_projects() -> list[dict]:
    """Every project, active first, for the QC settings project picker."""
    return db.run_query(
        "SELECT project_id, project_alias, project_title, project_status, transcription "
        "FROM projects ORDER BY project_status = 'Completed', project_title"
    )


def get_project(project_id: int) -> dict | None:
    rows = db.run_query(
        "SELECT project_id, project_alias, project_title, project_status, transcription "
        "FROM projects WHERE project_id = %(pid)s", {'pid': project_id})
    return rows[0] if rows else None


def get_settings(project: dict) -> dict | None:
    """This project's qc_settings/transcription_qc_settings row, or None if
    it has not opened the QC page yet (no row created)."""
    table = SETTINGS_TABLE[int(project['transcription'])]
    rows = db.run_query(
        "SELECT * FROM {} WHERE project_id = %(pid)s".format(table),
        {'pid': project['project_id']},
    )
    return rows[0] if rows else None


def set_method(project: dict, method: str) -> None:
    """Set the project's qc_method, used for QC results saved from now on.
    Already-saved folders keep the method stamped on their qc_folders row."""
    if method not in qc.QC_METHODS:
        raise ValueError("unknown qc_method: {!r}".format(method))
    table = SETTINGS_TABLE[int(project['transcription'])]
    db.query_database_insert(
        "UPDATE {} SET qc_method = %(method)s WHERE project_id = %(pid)s".format(table),
        {'method': method, 'pid': project['project_id']},
    )


# A lock is a QC row with an owner and no pass/fail result yet: the same rule
# as the "Folders with QC in Progress" lists on /qc and /qc_transcription.
_LOCKED = "q.qc_by IS NOT NULL AND (q.qc_status IS NULL OR q.qc_status NOT IN (0, 1))"


def locks() -> list[dict]:
    """Folders held in QC, oldest first. `kind` picks the reset route:
    'folder' (image QC on folders), 'transcription_folder' (image QC on
    transcription folders, keyed by UUID), 'text' (transcription-text QC on
    one source)."""
    rows = db.run_query(
        "SELECT 'folder' AS kind, CAST(f.folder_id AS CHAR) AS folder_id, NULL AS source_id, "
        "  NULL AS source_name, f.project_folder AS folder_name, p.project_id, p.project_alias, "
        "  p.project_title, u.username AS qc_by, q.updated_at, "
        "  DATEDIFF(NOW(), q.updated_at) AS days_since "
        "FROM qc_folders q JOIN folders f ON f.folder_id = q.folder_id "
        "  JOIN projects p ON p.project_id = f.project_id "
        "  LEFT JOIN users u ON u.user_id = q.qc_by "
        "WHERE " + _LOCKED
    )
    rows += db.run_query(
        "SELECT 'transcription_folder' AS kind, f.folder_transcription_id AS folder_id, "
        "  NULL AS source_id, NULL AS source_name, f.folder AS folder_name, p.project_id, "
        "  p.project_alias, p.project_title, u.username AS qc_by, q.updated_at, "
        "  DATEDIFF(NOW(), q.updated_at) AS days_since "
        "FROM qc_folders q JOIN transcription_folders f ON f.folder_transcription_id = q.folder_uid "
        "  JOIN projects p ON p.project_id = f.project_id "
        "  LEFT JOIN users u ON u.user_id = q.qc_by "
        "WHERE " + _LOCKED
    )
    rows += db.run_query(
        "SELECT 'text' AS kind, f.folder_transcription_id AS folder_id, "
        "  q.transcription_source_id AS source_id, s.transcription_source_name AS source_name, "
        "  f.folder AS folder_name, p.project_id, p.project_alias, p.project_title, "
        "  u.username AS qc_by, q.updated_at, DATEDIFF(NOW(), q.updated_at) AS days_since "
        "FROM transcription_qc_folders q "
        "  JOIN transcription_folders f ON f.folder_transcription_id = q.folder_transcription_id "
        "  JOIN projects p ON p.project_id = f.project_id "
        "  LEFT JOIN transcription_sources s ON s.transcription_source_id = q.transcription_source_id "
        "  LEFT JOIN users u ON u.user_id = q.qc_by "
        "WHERE " + _LOCKED
    )
    rows.sort(key=lambda r: r['updated_at'])
    return rows
