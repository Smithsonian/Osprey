"""Folder QC decision: pass/fail from the sampled files' issue counts."""

from __future__ import annotations

from osprey import audit
from osprey.db import query_database_insert, run_query

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


# qc_settings.qc_method: which pass/fail rule a project uses. The method a
# saved result was decided with is stamped on qc_folders.qc_method.
QC_METHOD_WEIGHTED = 'weighted'
QC_METHOD_CUMULATIVE = 'cumulative'
QC_METHODS = {
    QC_METHOD_WEIGHTED: 'Weighted (critical gate + weighted major/minor)',
    QC_METHOD_CUMULATIVE: 'Cumulative (critical / +major / +minor thresholds)',
}
DEFAULT_QC_METHOD = QC_METHOD_WEIGHTED


def qc_method(settings):
    """The project's QC method; settings rows from before the column existed use the default."""
    method = settings.get('qc_method') or DEFAULT_QC_METHOD
    if method not in QC_METHODS:
        raise ValueError("unknown qc_method: {!r}".format(method))
    return method


def _checks(critical, major, minor, settings):
    """The (label, issues, limit) checks for the project's QC method.

    weighted: critical issues are a hard gate checked alone against
    qc_threshold_critical. Major and minor issues are blended into a single
    weighted rate - minor weighted less punishing than major via
    w_major/w_minor - compared against weighted_rate.

    cumulative: each issue also counts against the thresholds of the less
    severe categories - critical vs qc_threshold_critical, critical + major
    vs qc_threshold_major, critical + major + minor vs qc_threshold_minor.
    """
    method = qc_method(settings)
    checks = [('Critical', critical, float(settings['qc_threshold_critical']))]
    if method == QC_METHOD_CUMULATIVE:
        checks.append(('Critical + major', critical + major, float(settings['qc_threshold_major'])))
        checks.append(('Critical + major + minor', critical + major + minor,
                       float(settings['qc_threshold_minor'])))
    else:
        weighted_issues = major * float(settings['w_major']) + minor * float(settings['w_minor'])
        checks.append(('Weighted major + minor', weighted_issues, float(settings['weighted_rate'])))
    return method, checks


def folder_passes_qc(sample_size, critical, major, minor, settings):
    """Return True if the folder passes QC under the project's qc_method.

    Every check's issue count, as a percentage of the sample, must not
    exceed its threshold (see _checks). Only exceeding a threshold fails
    (equal passes).
    """
    if sample_size <= 0:
        raise ValueError("QC sample is empty")
    _, checks = _checks(critical, major, minor, settings)
    return all(issues / sample_size * 100 <= limit for _, issues, limit in checks)


def qc_math(sample_size, critical, major, minor, settings):
    """Break down the folder_passes_qc computation for display.

    Same checks as folder_passes_qc, but returns each check's issues,
    percentage, threshold and pass/fail (rounded for display; pass/fail uses
    the unrounded numbers) so a results page can show how the result was
    reached.
    """
    method, checks = _checks(critical, major, minor, settings)
    rows = []
    for label, issues, limit in checks:
        pct = issues / sample_size * 100 if sample_size > 0 else 0
        rows.append({'label': label, 'issues': round(issues, 3), 'pct': round(pct, 3),
                     'limit': limit, 'passed': pct <= limit})
    result = {
        'method': method, 'method_label': QC_METHODS[method],
        'sample_size': sample_size,
        'critical': critical, 'major': major, 'minor': minor,
        'checks': rows,
        'passed': all(row['passed'] for row in rows),
    }
    if method == QC_METHOD_WEIGHTED:
        result['w_major'] = float(settings['w_major'])
        result['w_minor'] = float(settings['w_minor'])
        result['weighted_issues'] = rows[1]['issues']
    return result


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


def reset_folder_qc(folder_id, transcription):
    """Release a folder's image/file QC lock so it re-enters the queue.

    Transcription folders key qc_folders/qc_files/folders_badges by folder_uid
    (their UUID); regular folders by folder_id.
    """
    fold_id = "folder_uid" if transcription == 1 else "folder_id"
    query_database_insert(
        f"UPDATE qc_folders SET qc_status = 9, qc_by = NULL, qc_method = NULL WHERE {fold_id} = %(folder_id)s",
        {'folder_id': folder_id})
    query_database_insert(
        f"DELETE FROM qc_files WHERE {fold_id} = %(folder_id)s",
        {'folder_id': folder_id})
    query_database_insert(
        f"DELETE FROM folders_badges WHERE {fold_id} = %(folder_id)s AND badge_type = 'qc_status'",
        {'folder_id': folder_id})
    audit.record('update', 'folder', 'qc_reset', folder_ref=folder_id,
                 transcription=transcription == 1)


def reset_transcription_text_qc(folder_id, source_id):
    """Release a folder's transcription-text QC lock for one source."""
    params = {'folder_id': folder_id, 'source_id': source_id}
    query_database_insert(
        "UPDATE transcription_qc_folders SET qc_status = 9, qc_by = NULL, qc_method = NULL "
        " WHERE folder_transcription_id = %(folder_id)s "
        "   AND transcription_source_id = %(source_id)s",
        params)
    query_database_insert(
        "DELETE FROM transcription_qc "
        " WHERE folder_transcription_id = %(folder_id)s "
        "   AND transcription_source_id = %(source_id)s",
        params)
    query_database_insert(
        "DELETE FROM folders_badges "
        " WHERE folder_uid = %(folder_id)s "
        "   AND badge_type = 'transcription_qc_status' "
        "   AND folder_transcription_id = %(source_id)s",
        params)
    audit.record('update', 'folder', 'qc_reset', folder_ref=folder_id, transcription=True,
                 note="transcription source {}".format(source_id))
