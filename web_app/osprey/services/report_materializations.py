"""Helpers for DB-tracked report materialization status + artifacts.

This module is intentionally thin: it only reads/writes the
`report_materializations` table and does not execute report SQL.
Materialization execution is done by a scheduled process (cron/event).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from osprey.db import run_query


def get_materialization(project_id: int, report_id: str) -> Optional[Dict[str, Any]]:
    rows = run_query(
        """
        SELECT
            project_id,
            report_id,
            status,
            requested_by,
            freshness_sla_seconds,
            last_started_at,
            last_succeeded_at,
            last_failed_at,
            source_updated_at,
            duration_ms,
            row_count,
            error_message,
            artifact_path_csv,
            artifact_path_xlsx,
            materialized_table_name,
            updated_at
        FROM report_materializations
        WHERE project_id = %(project_id)s AND report_id = %(report_id)s
        """,
        {"project_id": project_id, "report_id": report_id},
    )
    return rows[0] if rows else None


def ensure_row(project_id: int, report_id: str, freshness_sla_seconds: int = 86400) -> bool:
    """Create the tracking row if it doesn't exist."""
    return run_query(
        """
        INSERT INTO report_materializations (project_id, report_id, freshness_sla_seconds, status)
        VALUES (%(project_id)s, %(report_id)s, %(freshness_sla_seconds)s, 'queued')
        ON DUPLICATE KEY UPDATE
            freshness_sla_seconds = VALUES(freshness_sla_seconds)
        """,
        {
            "project_id": project_id,
            "report_id": report_id,
            "freshness_sla_seconds": freshness_sla_seconds,
        },
        return_val=False,
    )


def request_refresh(project_id: int, report_id: str, requested_by: Optional[str]) -> bool:
    """Mark a report as queued unless already running.

    This is safe to call from the web app. The actual refresh is performed
    by a scheduled process which looks for queued rows.
    """
    return run_query(
        """
        INSERT INTO report_materializations (project_id, report_id, status, requested_by)
        VALUES (%(project_id)s, %(report_id)s, 'queued', %(requested_by)s)
        ON DUPLICATE KEY UPDATE
            requested_by = VALUES(requested_by),
            status = CASE
                WHEN status = 'running' THEN status
                ELSE 'queued'
            END,
            error_message = NULL
        """,
        {"project_id": project_id, "report_id": report_id, "requested_by": requested_by},
        return_val=False,
    )

