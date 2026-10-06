"""Folder QC decision: pass/fail from the sampled files' issue counts."""

from __future__ import annotations

from osprey.db import run_query

# Labels produced by the error_files queries in app.py (file_qc / qc_results 1-3)
_SEVERITY_LABELS = {
    'Critical Issue': 'critical',
    'Major Issue': 'major',
    'Minor Issue': 'minor',
}


def count_issues(error_files, key):
    """Count rows per severity. `key` is the column holding the label ('file_qc' or 'qc_results')."""
    counts = {'critical': 0, 'major': 0, 'minor': 0}
    for row in error_files or []:
        severity = _SEVERITY_LABELS.get(row.get(key))
        if severity:
            counts[severity] += 1
    return counts


def folder_passes_qc(sample_size, critical, major, minor, settings):
    """Return True if the folder passes QC.

    Severities are cumulative: each issue also counts against the thresholds
    of less severe categories, so the minor threshold caps all issues combined.
    Only exceeding a threshold fails (equal passes).
    """
    if sample_size <= 0:
        raise ValueError("QC sample is empty")

    def pct(n):
        return n / sample_size * 100

    checks = (
        (pct(critical), settings['qc_threshold_critical']),
        (pct(critical + major), settings['qc_threshold_major']),
        (pct(critical + major + minor), settings['qc_threshold_minor']),
    )
    return all(p <= float(limit) for p, limit in checks)


def load_folder_qc_counts(folder_id, transcription):
    """Read the folder's QC sample from qc_files.

    Returns {'no_files', 'unrated', 'critical', 'major', 'minor'}.
    Unrated = file_qc 9 (or NULL) = not yet reviewed.
    """
    # Transcription folders are keyed by UUID in folder_uid
    fold_id = "folder_uid" if transcription else "folder_id"
    row = run_query(
        "SELECT COUNT(*) AS no_files, "
        "  COALESCE(SUM(file_qc IS NULL OR file_qc = 9), 0) AS unrated, "
        "  COALESCE(SUM(file_qc = 1), 0) AS critical, "
        "  COALESCE(SUM(file_qc = 2), 0) AS major, "
        "  COALESCE(SUM(file_qc = 3), 0) AS minor "
        f"FROM qc_files WHERE {fold_id} = %(folder_id)s",
        {'folder_id': folder_id},
    )[0]
    # MySQL SUM() returns Decimal
    return {k: int(v) for k, v in row.items()}
