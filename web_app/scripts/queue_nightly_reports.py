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
    if rows is False:
        raise RuntimeError("Failed to list pregenerated reports from data_reports")
    return rows or []


def queue_all(*, requested_by: str = "nightly") -> int:
    reports = list_pregenerated_reports()
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
