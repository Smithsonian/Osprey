"""QC settings lookup for the sysadmin QC tab: one project's sampling level,
percent, and critical/major/minor thresholds.

Regular projects keep their row in qc_settings; transcription projects in
transcription_qc_settings (same columns in both — see the /qc and
/qc_transcription routes in app.py, which create the row on first visit).
This module only reads; a project that has never opened /qc has no row yet.
"""

from __future__ import annotations

from osprey import db

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
