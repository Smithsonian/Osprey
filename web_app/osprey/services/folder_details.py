"""Folder detail and file-check queries shared by the API and dashboard."""

import uuid

import pandas as pd

from osprey.db import run_query

CHECK_RESULTS_SQL = (
    "CASE WHEN c.check_results IS NULL THEN 'Pending' "
    "WHEN c.check_results = 9 THEN 'Pending' "
    "WHEN c.check_results = 0 THEN 'OK' "
    "WHEN c.check_results = 1 THEN 'Failed' END"
)

POST_RESULTS_SQL = (
    "CASE WHEN c.post_results IS NULL THEN 'Pending' "
    "WHEN c.post_results = 9 THEN 'Pending' "
    "WHEN c.post_results = 0 THEN 'Completed' "
    "WHEN c.post_results = 1 THEN 'Failed' ELSE 'Pending' END"
)


def parse_folder_id(folder_id_raw):
    """Return (folder_id, transcription). Raises ValueError if invalid."""
    if folder_id_raw is None:
        raise ValueError('folder_id is missing')
    try:
        return int(folder_id_raw), 0
    except (TypeError, ValueError):
        try:
            parsed = uuid.UUID(str(folder_id_raw), version=4)
            return str(parsed), 1
        except (ValueError, AttributeError) as err:
            raise ValueError('folder_id value not valid') from err


def get_folder_details_row(folder_id, transcription):
    if transcription == 1:
        rows = run_query(
            ("SELECT f.folder_transcription_id as folder_id, f.project_id, f.folder, "
             "   p.project_alias, f.status, f.previews, f.preview_type, "
             "   DATE_FORMAT(f.date, '%Y-%m-%d') as folder_date, "
             "   f.file_errors, f.error_info, "
             " CASE WHEN f.delivered_to_dams = 0 THEN 'Completed' "
             "              WHEN f.delivered_to_dams = 1 THEN 'Ready for DAMS' "
             "              WHEN f.delivered_to_dams = 9 THEN 'Pending' END as delivered_to_dams, "
             " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
             "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
             "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
             "          'QC Pending') as qc_status, "
             " p.transcription "
             " FROM transcription_folders f "
             " LEFT JOIN qc_folders qcf ON (f.folder_transcription_id = qcf.folder_uid), projects p "
             " WHERE f.folder_transcription_id = %(folder_id)s and f.project_id = p.project_id"),
            {'folder_id': folder_id},
        )
    else:
        rows = run_query(
            ("SELECT f.folder_id, f.project_id, f.project_folder as folder, "
             "   p.project_alias, f.status, f.previews, f.preview_type, "
             "   DATE_FORMAT(f.date, '%Y-%m-%d') as folder_date, "
             "   f.file_errors, f.error_info, "
             " CASE WHEN f.delivered_to_dams = 0 THEN 'Completed' "
             "              WHEN f.delivered_to_dams = 1 THEN 'Ready for DAMS' "
             "              WHEN f.delivered_to_dams = 9 THEN 'Pending' END as delivered_to_dams, "
             " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
             "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
             "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
             "          'QC Pending') as qc_status, "
             " p.transcription "
             " FROM folders f "
             " LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id), projects p "
             " WHERE f.folder_id = %(folder_id)s and f.project_id = p.project_id"),
            {'folder_id': folder_id},
        )
    if len(rows) != 1:
        return None
    return rows[0]


def list_project_file_checks(project_id):
    rows = run_query(
        ("SELECT settings_value as file_check FROM projects_settings "
         " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
        {'project_id': project_id},
    )
    return [row['file_check'] for row in rows]


def list_project_postprocessing(project_id):
    rows = run_query(
        ("SELECT settings_value as post_step FROM projects_settings "
         " WHERE project_setting = 'project_postprocessing' and project_id = %(project_id)s ORDER BY table_id"),
        {'project_id': project_id},
    )
    return [row['post_step'] for row in rows]


def list_folder_files_base(folder_id, transcription):
    if transcription == 1:
        return run_query(
            ("SELECT f.file_transcription_id as file_id, f.file_name, "
             " DATE_FORMAT(f.file_timestamp, '%Y-%m-%d %H:%i:%S') as file_timestamp, "
             " f.dams_uan, f.preview_image, "
             " DATE_FORMAT(f.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at, "
             " DATE_FORMAT(f.created_at, '%Y-%m-%d %H:%i:%S') AS created_at, m.md5 as tif_md5 "
             " FROM transcription_files f "
             " LEFT JOIN file_md5 m ON (f.file_transcription_id = m.file_uid) "
             " WHERE f.folder_transcription_id = %(folder_id)s "
             " ORDER BY f.file_name"),
            {'folder_id': folder_id},
        )
    return run_query(
        ("SELECT f.file_id, f.file_name, "
         " DATE_FORMAT(f.file_timestamp, '%Y-%m-%d %H:%i:%S') as file_timestamp, "
         " f.dams_uan, f.preview_image, "
         " DATE_FORMAT(f.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at, "
         " DATE_FORMAT(f.created_at, '%Y-%m-%d %H:%i:%S') AS created_at, m.md5 as tif_md5 "
         " FROM files f "
         " LEFT JOIN file_md5 m ON (f.file_id = m.file_id AND lower(m.filetype)='tif') "
         " WHERE f.folder_id = %(folder_id)s "
         " ORDER BY f.file_name"),
        {'folder_id': folder_id},
    )


def list_folder_file_check_rows(folder_id, transcription, project_id):
    if transcription == 1:
        return run_query(
            ("WITH checks AS ("
             "  SELECT settings_value as file_check FROM projects_settings "
             "  WHERE project_setting = 'project_checks' AND project_id = %(project_id)s"
             "), folder_files AS ("
             "  SELECT file_transcription_id as file_id FROM transcription_files "
             "  WHERE folder_transcription_id = %(folder_id)s"
             ") "
             "SELECT ff.file_id, d.file_check, "
             f" {CHECK_RESULTS_SQL} as check_results, "
             " c.check_info, DATE_FORMAT(c.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at "
             " FROM folder_files ff "
             " CROSS JOIN checks d "
             " LEFT JOIN transcription_files_checks c "
             "   ON (ff.file_id = c.file_transcription_id AND c.file_check = d.file_check)"),
            {'folder_id': folder_id, 'project_id': project_id},
        )
    return run_query(
        ("WITH checks AS ("
         "  SELECT settings_value as file_check FROM projects_settings "
         "  WHERE project_setting = 'project_checks' AND project_id = %(project_id)s"
         "), folder_files AS ("
         "  SELECT file_id FROM files WHERE folder_id = %(folder_id)s"
         ") "
         "SELECT ff.file_id, d.file_check, "
         f" {CHECK_RESULTS_SQL} as check_results, "
         " c.check_info, DATE_FORMAT(c.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at "
         " FROM folder_files ff "
         " CROSS JOIN checks d "
         " LEFT JOIN files_checks c "
         "   ON (ff.file_id = c.file_id AND c.file_check = d.file_check)"),
        {'folder_id': folder_id, 'project_id': project_id},
    )


def list_folder_file_postprocessing_rows(folder_id, transcription, project_id):
    """Cross-join of folder files x project postprocessing steps. Not supported for
    transcription folders (file_postprocessing has no transcription-pipeline
    counterpart) -- matches the original inline-query behavior."""
    if transcription == 1:
        return []
    return run_query(
        ("WITH steps AS ("
         "  SELECT settings_value as post_step FROM projects_settings "
         "  WHERE project_setting = 'project_postprocessing' AND project_id = %(project_id)s"
         "), folder_files AS ("
         "  SELECT file_id FROM files WHERE folder_id = %(folder_id)s"
         ") "
         "SELECT ff.file_id, d.post_step, "
         f" {POST_RESULTS_SQL} as post_results, "
         " c.post_info, DATE_FORMAT(c.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at "
         " FROM folder_files ff "
         " CROSS JOIN steps d "
         " LEFT JOIN file_postprocessing c "
         "   ON (ff.file_id = c.file_id AND c.post_step = d.post_step)"),
        {'folder_id': folder_id, 'project_id': project_id},
    )


def build_file_postprocessing_arrays(base_files, postproc_rows, project_postprocessing):
    """Attach ordered file_postprocessing arrays to each file dict."""
    by_file = {}
    for row in postproc_rows:
        file_id = row['file_id']
        by_file.setdefault(file_id, {})[row['post_step']] = {
            'post_step': row['post_step'],
            'post_results': row['post_results'],
            'post_info': row['post_info'],
            'updated_at': row['updated_at'],
        }

    files = []
    for file_row in base_files:
        file_id = file_row['file_id']
        steps_map = by_file.get(file_id, {})
        file_postprocessing = []
        for step_name in project_postprocessing:
            file_postprocessing.append(steps_map.get(step_name, {
                'post_step': step_name,
                'post_results': 'Pending',
                'post_info': None,
                'updated_at': None,
            }))
        entry = dict(file_row)
        entry['file_postprocessing'] = file_postprocessing
        files.append(entry)
    return files


def build_file_checks_arrays(base_files, check_rows, project_checks):
    """Attach ordered file_checks arrays to each file dict."""
    by_file = {}
    for row in check_rows:
        file_id = row['file_id']
        by_file.setdefault(file_id, {})[row['file_check']] = {
            'file_check': row['file_check'],
            'check_results': row['check_results'],
            'check_info': row['check_info'],
            'updated_at': row['updated_at'],
        }

    files = []
    for file_row in base_files:
        file_id = file_row['file_id']
        checks_map = by_file.get(file_id, {})
        file_checks = []
        for check_name in project_checks:
            file_checks.append(checks_map.get(check_name, {
                'file_check': check_name,
                'check_results': 'Pending',
                'check_info': None,
                'updated_at': None,
            }))
        entry = dict(file_row)
        entry['file_checks'] = file_checks
        files.append(entry)
    return files


def attach_checks_flat(folder_files_df, folder_id, transcription, filechecks_list):
    """Merge flat OK/Pending/Failed columns (legacy API response)."""
    for fcheck in filechecks_list:
        if transcription == 1:
            list_files = pd.DataFrame(run_query(
                ("SELECT f.file_transcription_id as file_id, "
                 "   CASE WHEN check_results = 0 THEN 'OK' "
                 "       WHEN check_results = 9 THEN 'Pending' "
                 "       WHEN check_results = 1 THEN 'Failed' "
                 "       ELSE 'Pending' END as {fcheck} "
                 " FROM transcription_files f "
                 " LEFT JOIN transcription_files_checks c "
                 "   ON (f.file_transcription_id=c.file_transcription_id AND c.file_check = %(file_check)s) "
                 " WHERE f.file_transcription_id in ("
                 "   select file_transcription_id from transcription_files "
                 "   where folder_transcription_id = %(folder_id)s)").format(fcheck=fcheck),
                {'file_check': fcheck, 'folder_id': folder_id},
            ))
        else:
            list_files = pd.DataFrame(run_query(
                ("SELECT f.file_id, "
                 "   CASE WHEN check_results = 0 THEN 'OK' "
                 "       WHEN check_results = 9 THEN 'Pending' "
                 "       WHEN check_results = 1 THEN 'Failed' "
                 "       ELSE 'Pending' END as {fcheck} "
                 " FROM files f LEFT JOIN files_checks c "
                 "   ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                 " WHERE f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                {'file_check': fcheck, 'folder_id': folder_id},
            ))
        if list_files.shape[0] > 0:
            folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
    return folder_files_df


def get_folder_files_payload(folder_id_raw):
    """Return folder JSON with files[].file_checks arrays, or (None, status_code, message)."""
    try:
        folder_id, transcription = parse_folder_id(folder_id_raw)
    except ValueError as err:
        return None, 400, str(err)

    folder_row = get_folder_details_row(folder_id, transcription)
    if folder_row is None:
        return None, 404, 'Folder not found'

    project_id = folder_row['project_id']
    project_checks = list_project_file_checks(project_id)
    project_postprocessing = list_project_postprocessing(project_id)
    base_files = list_folder_files_base(folder_id, transcription)
    check_rows = list_folder_file_check_rows(folder_id, transcription, project_id)
    postproc_rows = list_folder_file_postprocessing_rows(folder_id, transcription, project_id)
    files = build_file_checks_arrays(base_files, check_rows, project_checks)
    files = build_file_postprocessing_arrays(files, postproc_rows, project_postprocessing)

    payload = dict(folder_row)
    payload.pop('transcription', None)
    payload['project_checks'] = project_checks
    payload['project_postprocessing'] = project_postprocessing
    payload['files'] = files
    return payload, 200, None


def get_folder_qc_payload(folder_id_raw):
    """Return folder visual-QC sampling summary JSON, or (None, status_code, message)."""
    try:
        folder_id, transcription = parse_folder_id(folder_id_raw)
    except ValueError as err:
        return None, 400, str(err)

    folder_row = get_folder_details_row(folder_id, transcription)
    if folder_row is None:
        return None, 404, 'Folder not found'

    if transcription == 1:
        qc_files = run_query(
            "SELECT 1 FROM qc_files WHERE folder_uid = %(folder_id)s",
            {'folder_id': folder_id},
        )
    else:
        qc_files = run_query(
            "SELECT 1 FROM qc_files WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id},
        )

    if not qc_files:
        return {
            'folder_id': folder_id,
            'qc_checked': False,
            'qc_folder_info': None,
            'files': [],
        }, 200, None

    if transcription == 1:
        details = run_query(
            ("SELECT f.file_transcription_id as file_id, f.file_name, q.file_qc, q.qc_info "
             " FROM qc_files q, transcription_files f "
             " WHERE q.folder_uid = %(folder_id)s AND q.file_uid = f.file_transcription_id "
             " ORDER BY q.file_qc DESC"),
            {'folder_id': folder_id},
        )
        folder_info_rows = run_query(
            "SELECT qc_info FROM qc_folders WHERE folder_uid = %(folder_id)s",
            {'folder_id': folder_id},
        )
    else:
        details = run_query(
            ("SELECT f.file_id, f.file_name, q.file_qc, q.qc_info "
             " FROM qc_files q, files f "
             " WHERE q.folder_id = %(folder_id)s AND q.file_id = f.file_id "
             " ORDER BY q.file_qc DESC"),
            {'folder_id': folder_id},
        )
        folder_info_rows = run_query(
            "SELECT qc_info FROM qc_folders WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id},
        )

    return {
        'folder_id': folder_id,
        'qc_checked': True,
        'qc_folder_info': folder_info_rows[0]['qc_info'] if folder_info_rows else None,
        'files': [dict(row) for row in details],
    }, 200, None


def get_folder_transcription_qc_payload(folder_id_raw):
    """Return per-source transcription-QC sampling summaries."""
    try:
        folder_id, transcription = parse_folder_id(folder_id_raw)
    except ValueError as err:
        return None, 400, str(err)

    folder_row = get_folder_details_row(folder_id, transcription)
    if folder_row is None:
        return None, 404, 'Folder not found'

    if transcription != 1:
        return {
            'folder_id': folder_id,
            'qc_checked': False,
            'sources': [],
        }, 200, None

    source_rows = run_query(
        ("SELECT q.transcription_source_id as source_id, "
         "       s.transcription_source_name as source_name, "
         "       CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
         "            WHEN q.qc_status = 1 THEN 'QC Failed' "
         "            WHEN q.qc_status = 9 THEN 'QC Pending' "
         "            ELSE 'QC Pending' END AS qc_status, "
         "       q.qc_status as qc_status_value, q.qc_info, q.qc_ip, "
         "       u.username as qc_by, "
         "       DATE_FORMAT(q.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at "
         " FROM transcription_qc_folders q "
         " JOIN transcription_sources s "
         "   ON (q.transcription_source_id = s.transcription_source_id) "
         " LEFT JOIN users u ON (q.qc_by = u.user_id) "
         " WHERE q.folder_transcription_id = %(folder_id)s "
         " ORDER BY s.transcription_source_name"),
        {'folder_id': folder_id},
    )

    if not source_rows:
        return {
            'folder_id': folder_id,
            'qc_checked': False,
            'sources': [],
        }, 200, None

    detail_rows = run_query(
        ("SELECT q.transcription_source_id as source_id, "
         "       f.file_transcription_id as file_id, f.file_name, "
         "       q.qc_results, q.qc_notes "
         " FROM transcription_qc q "
         " JOIN transcription_files f "
         "   ON (q.file_transcription_id = f.file_transcription_id) "
         " WHERE q.folder_transcription_id = %(folder_id)s "
         " ORDER BY q.transcription_source_id, q.qc_results DESC, f.file_name"),
        {'folder_id': folder_id},
    )

    files_by_source = {}
    for row in detail_rows:
        files_by_source.setdefault(row['source_id'], []).append({
            'file_id': row['file_id'],
            'file_name': row['file_name'],
            'qc_results': row['qc_results'],
            'qc_notes': row['qc_notes'],
        })

    sources = []
    for row in source_rows:
        source_id = row['source_id']
        sources.append({
            'source_id': source_id,
            'source_name': row['source_name'],
            'qc_status': row['qc_status'],
            'qc_status_value': row['qc_status_value'],
            'qc_folder_info': row['qc_info'],
            'qc_by': row['qc_by'],
            'qc_ip': row['qc_ip'],
            'updated_at': row['updated_at'],
            'files': files_by_source.get(source_id, []),
        })

    return {
        'folder_id': folder_id,
        'qc_checked': True,
        'sources': sources,
    }, 200, None
