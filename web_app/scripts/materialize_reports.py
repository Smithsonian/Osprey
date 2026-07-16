#!/usr/bin/env python3
"""Scheduled materialization for pregenerated reports.

This script is meant to be invoked out-of-band (cron, systemd timer, etc.).
It pulls queued/runnable entries from `report_materializations`, executes the
corresponding `data_reports.query` for a (project_id, report_id), and writes
CSV/XLSX artifacts under `static/reports/`, then updates status/metadata.

It intentionally does NOT run as part of a web request, avoiding HTTP timeouts.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd

import settings
from logger import logger
from osprey.db import run_query
from osprey.services import reports as report_service


def _set_status(
    project_id: int,
    report_id: str,
    *,
    status: str,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    row_count: Optional[int] = None,
    source_updated_at: Optional[str] = None,
    artifact_path_csv: Optional[str] = None,
    artifact_path_xlsx: Optional[str] = None,
    materialized_table_name: Optional[str] = None,
) -> None:
    run_query(
        """
        INSERT INTO report_materializations (
            project_id,
            report_id,
            status,
            last_started_at,
            last_succeeded_at,
            last_failed_at,
            error_message,
            duration_ms,
            row_count,
            source_updated_at,
            artifact_path_csv,
            artifact_path_xlsx,
            materialized_table_name
        )
        VALUES (
            %(project_id)s,
            %(report_id)s,
            %(status)s,
            CASE WHEN %(status)s = 'running' THEN CURRENT_TIMESTAMP ELSE NULL END,
            CASE WHEN %(status)s = 'succeeded' THEN CURRENT_TIMESTAMP ELSE NULL END,
            CASE WHEN %(status)s = 'failed' THEN CURRENT_TIMESTAMP ELSE NULL END,
            %(error_message)s,
            %(duration_ms)s,
            %(row_count)s,
            %(source_updated_at)s,
            %(artifact_path_csv)s,
            %(artifact_path_xlsx)s,
            %(materialized_table_name)s
        )
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            last_started_at = CASE WHEN VALUES(status) = 'running' THEN CURRENT_TIMESTAMP ELSE last_started_at END,
            last_succeeded_at = CASE WHEN VALUES(status) = 'succeeded' THEN CURRENT_TIMESTAMP ELSE last_succeeded_at END,
            last_failed_at = CASE WHEN VALUES(status) = 'failed' THEN CURRENT_TIMESTAMP ELSE last_failed_at END,
            error_message = VALUES(error_message),
            duration_ms = VALUES(duration_ms),
            row_count = VALUES(row_count),
            source_updated_at = VALUES(source_updated_at),
            artifact_path_csv = VALUES(artifact_path_csv),
            artifact_path_xlsx = VALUES(artifact_path_xlsx),
            materialized_table_name = VALUES(materialized_table_name)
        """,
        {
            "project_id": project_id,
            "report_id": report_id,
            "status": status,
            "error_message": error_message,
            "duration_ms": duration_ms,
            "row_count": row_count,
            "source_updated_at": source_updated_at,
            "artifact_path_csv": artifact_path_csv,
            "artifact_path_xlsx": artifact_path_xlsx,
            "materialized_table_name": materialized_table_name,
        },
        return_val=False,
    )


def _safe_identifier(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", raw or "").strip("_").lower()
    return cleaned[:48] if cleaned else "report"


def _materialized_table_name(project_id: int, report: dict) -> str:
    materialized_view = report.get("materialized_view") or f"report_{report.get('report_id')}"
    return f"rptmat_p{int(project_id)}_{_safe_identifier(str(materialized_view))}"


def _table_exists(table_name: str) -> bool:
    rows = run_query(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %(table_name)s
        LIMIT 1
        """,
        {"table_name": table_name},
    )
    return bool(rows)


def _ensure_table(table_name: str, select_sql: str) -> None:
    if _table_exists(table_name):
        return
    run_query(
        f"CREATE TABLE `{table_name}` AS {select_sql} LIMIT 0",
        return_val=False,
        log_vals=False,
    )


def _claim_next_job() -> Optional[dict]:
    # Best-effort claim: flip one queued row to running using a single UPDATE
    # and then read it back. This avoids requiring SELECT ... FOR UPDATE.
    updated = run_query(
        """
        UPDATE report_materializations
        SET status = 'running', last_started_at = CURRENT_TIMESTAMP, error_message = NULL
        WHERE status = 'queued'
        ORDER BY updated_at ASC
        LIMIT 1
        """,
        return_val=False,
    )
    if not updated:
        return None

    rows = run_query(
        """
        SELECT project_id, report_id
        FROM report_materializations
        WHERE status = 'running'
        ORDER BY last_started_at DESC
        LIMIT 1
        """
    )
    return rows[0] if rows else None


def _cleanup_old_artifacts(materialized_view: str, keep_rel_paths: set[str], retain_days: int = 7) -> None:
    """Remove prior CSV/XLSX artifacts for this report older than retain_days."""
    reports_dir = Path("static/reports")
    if not reports_dir.is_dir():
        return
    prefix = f"{materialized_view}_"
    cutoff = time.time() - (retain_days * 86400)
    keep_names = {Path(p).name for p in keep_rel_paths if p}
    for path in reports_dir.iterdir():
        if not path.is_file():
            continue
        if not path.name.startswith(prefix):
            continue
        if path.suffix.lower() not in {".csv", ".xlsx"}:
            continue
        if path.name in keep_names:
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            logger.info(f"materialize_reports: removed old artifact {path}")
        except OSError:
            logger.exception(f"materialize_reports: failed to remove {path}")


def _materialize_one(project_id: int, report_id: str) -> None:
    start = time.time()
    report = report_service.get_project_report(project_id, report_id)
    if not report:
        _set_status(project_id, report_id, status="failed", error_message="Report not found in data_reports")
        return

    try:
        # Compute freshness metadata (best effort).
        source_updated_at = None
        try:
            source_updated_at = str(report_service.get_report_last_updated(report))
        except Exception:
            source_updated_at = None

        # Ensure static/reports exists.
        Path("static/reports").mkdir(parents=True, exist_ok=True)

        rep_timestamp = time.localtime()
        ts_compact = time.strftime("%Y%m%d_%H%M%S", rep_timestamp)

        materialized_view = report.get("materialized_view") or f"report_{report_id}"
        rel_csv = f"reports/{materialized_view}_{ts_compact}.csv"
        rel_xlsx = f"reports/{materialized_view}_{ts_compact}.xlsx"
        abs_csv = os.path.join("static", rel_csv)
        abs_xlsx = os.path.join("static", rel_xlsx)

        table_name = _materialized_table_name(project_id, report)
        select_sql = str(report["query"]).strip().rstrip(";")
        _ensure_table(table_name, select_sql)
        run_query(f"TRUNCATE TABLE `{table_name}`", return_val=False, log_vals=False)
        run_query(f"INSERT INTO `{table_name}` {select_sql}", return_val=False, log_vals=False)

        data = run_query(f"SELECT * FROM `{table_name}`", log_vals=False)
        df = pd.DataFrame(data if data else [])
        df.to_csv(abs_csv, index=False)
        df.to_excel(abs_xlsx, index=False)

        _cleanup_old_artifacts(str(materialized_view), {rel_csv, rel_xlsx})

        duration_ms = int((time.time() - start) * 1000)
        _set_status(
            project_id,
            report_id,
            status="succeeded",
            duration_ms=duration_ms,
            row_count=len(df.index),
            source_updated_at=source_updated_at,
            artifact_path_csv=rel_csv,
            artifact_path_xlsx=rel_xlsx,
            error_message=None,
            materialized_table_name=table_name,
        )
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        _set_status(
            project_id,
            report_id,
            status="failed",
            duration_ms=duration_ms,
            error_message=str(exc),
            materialized_table_name=_materialized_table_name(project_id, report) if report else None,
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize queued reports to CSV/XLSX artifacts.")
    parser.add_argument("--once", action="store_true", help="Run at most one queued job then exit.")
    parser.add_argument(
        "--until-empty",
        action="store_true",
        help="Drain all queued jobs then exit (for overnight cron).",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        help="If >0, keep polling every N seconds (use with --until-empty to idle between jobs).",
    )
    args = parser.parse_args()

    # Touch settings so env is loaded similarly to app.
    _ = settings.host

    def run_one() -> bool:
        job = _claim_next_job()
        if not job:
            logger.info("materialize_reports: no queued jobs")
            return False
        pid = int(job["project_id"])
        rid = str(job["report_id"])
        logger.info(f"materialize_reports: running job project_id={pid} report_id={rid}")
        try:
            _materialize_one(pid, rid)
            logger.info(f"materialize_reports: succeeded project_id={pid} report_id={rid}")
        except Exception:
            logger.exception(f"materialize_reports: failed project_id={pid} report_id={rid}")
        return True

    if args.until_empty:
        poll_seconds = args.loop if args.loop > 0 else 0
        while True:
            ran = run_one()
            if not ran:
                return 0
            if poll_seconds:
                time.sleep(poll_seconds)
    elif args.loop and args.loop > 0:
        while True:
            ran = run_one()
            if args.once and ran:
                return 0
            time.sleep(args.loop)
    else:
        run_one()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

