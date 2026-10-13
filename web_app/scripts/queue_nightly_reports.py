#!/usr/bin/env python3
"""Queue all pregenerated data_reports for overnight materialization.

Intended to run from cron before scripts/materialize_reports.py drains the
queue. Safe to re-run: reports already `running` are left alone.
"""

from __future__ import annotations

import sys

import settings
from logger import logger
from osprey.db import run_query
from osprey.services import report_materializations as materializations
from osprey.services import sysadmin_reports
from osprey.services import sysadmin_stats
from osprey.services import transcription_profile


def list_pregenerated_reports() -> list[dict]:
    rows = run_query(
        """
        SELECT project_id, report_id, report_title
        FROM data_reports
        WHERE pregenerated = 1
        ORDER BY project_id, report_id
        """,
        log_vals=False,
    )
    return rows or []


def list_transcription_profile_jobs() -> list[dict]:
    """One built-in transcription_profile job per transcription project."""
    rows = run_query(
        "SELECT project_id FROM projects WHERE transcription = 1 ORDER BY project_id",
        log_vals=False,
    )
    return [
        {"project_id": r["project_id"], "report_id": transcription_profile.REPORT_ID,
         "report_title": "Transcription profile"}
        for r in rows or []
    ]


def list_stat_jobs() -> list[dict]:
    """One built-in job per sysadmin stat (not tied to a project)."""
    return [
        {"project_id": sysadmin_stats.STAT_PROJECT_ID, "report_id": sysadmin_stats.report_id_for(job_id),
         "report_title": job["title"]}
        for job_id, job in sysadmin_stats.STAT_JOBS.items()
    ]


def list_sysadmin_report_jobs() -> list[dict]:
    """Pregenerated sysadmin-only reports; none until db/sysadmin_reports.sql is applied."""
    if not sysadmin_reports.table_exists():
        return []
    rows = run_query(
        "SELECT report_id, title FROM sysadmin_reports WHERE pregenerated = 1 ORDER BY report_id",
        log_vals=False,
    )
    return [
        {"project_id": sysadmin_reports.MATERIALIZATION_PROJECT_ID,
         "report_id": sysadmin_reports.materialization_id(r["report_id"]),
         "report_title": r["title"]}
        for r in rows or []
    ]


def queue_all(*, requested_by: str = "nightly") -> int:
    # Stat jobs last: the queue drains oldest-first, so reports run before them.
    reports = (list_pregenerated_reports() + list_transcription_profile_jobs()
               + list_sysadmin_report_jobs() + list_stat_jobs())
    if not reports:
        logger.info("queue_nightly_reports: no pregenerated reports found")
        return 0

    queued = 0
    for report in reports:
        project_id = int(report["project_id"])
        report_id = str(report["report_id"])
        ok = materializations.request_refresh(
            project_id, report_id, requested_by=requested_by
        )
        if not ok:
            logger.error(
                "queue_nightly_reports: failed to queue "
                f"project_id={project_id} report_id={report_id}"
            )
            continue
        queued += 1
        logger.info(
            "queue_nightly_reports: queued "
            f"project_id={project_id} report_id={report_id} "
            f"title={report.get('report_title')!r}"
        )
    return queued


def main() -> int:
    _ = settings.host
    try:
        count = queue_all()
    except Exception:
        logger.exception("queue_nightly_reports: failed")
        return 1
    logger.info(f"queue_nightly_reports: queued {count} report(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
