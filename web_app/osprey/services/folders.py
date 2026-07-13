"""Folder list queries shared by the dashboard and API."""

from osprey.db import run_query


def list_for_project(project_id, transcription, include_previews=True):
    """Return folders for a project in API/dashboard JSON shape."""
    if transcription == 1:
        previews_select = "f.previews, " if include_previews else ""
        previews_group = ", f.previews" if include_previews else ""
        return run_query(
            ("SELECT "
             "f.folder_transcription_id as folder_id, f.project_id, f.folder, "
             "f.folder_path, f.status, "
             + previews_select +
             "f.preview_type, "
             "f.error_info, date_format(f.date, '%%Y-%%m-%%d') as capture_date, "
             "f.no_files, f.file_errors, "
             " CASE WHEN f.delivered_to_dams = 1 THEN 0 ELSE 9 END as delivered_to_dams, "
             " COALESCE(CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
             "         WHEN q.qc_status = 1 THEN 'QC Failed' "
             "         WHEN q.qc_status = 9 THEN 'QC Pending' END, 'QC Pending') as qc_status,"
             " GROUP_CONCAT(b.badge_text ORDER BY b.badge_text SEPARATOR ',') as badges"
             " FROM transcription_folders f LEFT JOIN qc_folders q ON (f.folder_transcription_id = q.folder_uid)"
             "     LEFT JOIN folders_badges b ON (f.folder_transcription_id = b.folder_uid) "
             " WHERE project_id = %(project_id)s"
             " GROUP BY f.folder_transcription_id, f.project_id, f.folder, f.folder_path, "
             "      f.status, f.preview_type, f.error_info, f.date, f.no_files,"
             "      f.file_errors, q.qc_status"
             + previews_group +
             " ORDER BY f.date DESC, f.folder DESC"),
            {'project_id': project_id},
        )
    previews_select = "f.previews, " if include_previews else ""
    previews_group = ", f.previews" if include_previews else ""
    return run_query(
        ("SELECT "
         "f.folder_id, f.project_id, f.project_folder as folder, "
         "f.folder_path, f.status, "
         + previews_select +
         "f.preview_type, "
         "f.error_info, date_format(f.date, '%%Y-%%m-%%d') as capture_date, "
         "f.no_files, f.file_errors, "
         " CASE WHEN f.delivered_to_dams = 1 THEN 0 ELSE 9 END as delivered_to_dams, "
         " COALESCE(CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
         "         WHEN q.qc_status = 1 THEN 'QC Failed' "
         "         WHEN q.qc_status = 9 THEN 'QC Pending' END, 'QC Pending') as qc_status,"
         " GROUP_CONCAT(b.badge_text ORDER BY b.badge_text SEPARATOR ',') as badges"
         " FROM folders f LEFT JOIN qc_folders q ON (f.folder_id = q.folder_id)"
         "     LEFT JOIN folders_badges b ON (f.folder_id = b.folder_id) "
         " WHERE project_id = %(project_id)s"
         " GROUP BY f.folder_id, f.project_id, f.project_folder, f.folder_path, "
         "      f.status, f.preview_type, f.error_info, f.date, f.no_files,"
         "      f.file_errors, q.qc_status"
         + previews_group +
         " ORDER BY f.date DESC, f.project_folder DESC"),
        {'project_id': project_id},
    )


def list_for_project_api(project_id, transcription):
    """Folder list for GET /api/projects/<alias> (includes previews for dashboard filters)."""
    return list_for_project(project_id, transcription, include_previews=True)
