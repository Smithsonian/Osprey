"""File detail, search, and DAMS-update queries for the dashboard web views."""

from uuid import UUID

import pandas as pd

from osprey.db import query_database_insert, run_query


def check_file_id_transcription(file_id=None):
    if file_id is None:
        return False
    else:
        try:
            file_uid = UUID(file_id, version=4)
        except ValueError:
            return False
    file_id = run_query(
        "SELECT file_transcription_id as file_id FROM transcription_files WHERE file_transcription_id = %(uid)s",
        {'uid': str(file_uid)})
    if len(file_id) == 0:
        return False
    else:
        return file_id[0]['file_id']


def get_folder_info(file_id):
    rows = run_query(
        "SELECT * FROM folders WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)",
        {'file_id': file_id})
    return rows[0] if rows else None


def get_file_details(folder_id, file_id):
    rows = run_query(("WITH data AS ("
                        "         SELECT file_id, "
                        "             preview_image as preview_image_ext, "
                        "             folder_id, file_name, dams_uan, file_ext, "
                        "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(NOW(), created_at) as datediff "
                        "             FROM files "
                        "                 WHERE folder_id = %(folder_id)s AND folder_id IN (SELECT folder_id FROM folders)"
                        " UNION "
                        "         SELECT file_id, preview_image as preview_image_ext, "
                        "                folder_id, file_name, dams_uan, file_ext, "
                        "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(created_at, NOW()) as datediff "
                        "             FROM files "
                        "                 WHERE folder_id = %(folder_id)s AND folder_id NOT IN (SELECT folder_id FROM folders)"
                        "             ORDER BY file_name"
                        "),"
                        "data2 AS (SELECT file_id, file_ext, preview_image_ext, folder_id, file_name, dams_uan, created_at, datediff, "
                        "         lag(file_id,1) over (order by file_name) prev_id,"
                        "         lead(file_id,1) over (order by file_name) next_id "
                        " FROM data)"
                        " SELECT "
                        " file_id, "
                        " preview_image_ext, folder_id, file_name, dams_uan, prev_id, next_id, file_ext, created_at, datediff "
                        " FROM data2 WHERE file_id = %(file_id)s LIMIT 1"),
                        {'folder_id': folder_id, 'file_id': file_id})
    return rows[0]


def get_project_alias(project_id):
    row = run_query(("SELECT COALESCE(project_alias, CAST(project_id AS char)) as project_id FROM projects "
                    " WHERE project_id = %(project_id)s"),
                   {'project_id': project_id})[0]
    return row['project_id']


def get_file_checks(file_id):
    return run_query(("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                        " ELSE check_info END AS check_info "
                        " FROM files_checks WHERE file_id = %(file_id)s"),
                        {'file_id': file_id})


def get_file_postprocessing(file_id):
    return run_query(("SELECT post_step, post_results, CASE WHEN post_info = '' THEN 'Step completed.' "
                        " WHEN post_info IS NULL THEN 'Step completed.' "
                        " ELSE post_info END AS post_info "
                        " FROM file_postprocessing WHERE file_id = %(file_id)s"),
                        {'file_id': file_id})


def get_file_metadata(file_id, file_ext):
    return pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                     " FROM files_exif "
                                     " WHERE file_id = %(file_id)s AND "
                                     "       lower(filetype) = %(file_ext)s AND "
                                     "       lower(taggroup) != 'system' "
                                     " ORDER BY taggroup, tag "),
                                    {'file_id': str(file_id), 'file_ext': file_ext}))


def get_file_links(file_id):
    return run_query("SELECT link_name, link_url, link_aria FROM files_links WHERE file_id = %(file_id)s ",
                        {'file_id': file_id})


def get_folder_info_transcription(file_id):
    rows = run_query(
        """SELECT * FROM transcription_folders WHERE folder_transcription_id IN
            (SELECT folder_transcription_id as folder_id FROM transcription_files WHERE file_transcription_id = %(file_id)s)""",
        {'file_id': file_id})
    return rows[0] if rows else None


def get_project_transcription_flag(project_id):
    row = run_query("SELECT transcription FROM projects WHERE project_id = %(project_id)s", {'project_id': project_id})[0]
    return int(row['transcription'])


def get_transcription_sources(project_id):
    return run_query(
        "SELECT transcription_source_id, transcription_source_name, "
        "CONCAT(transcription_source_notes, ' ', transcription_source_date) as source_notes "
        "FROM transcription_sources WHERE project_id = %(project_id)s",
        {'project_id': project_id})


def get_transcription_text_table(source_id, file_id):
    return pd.DataFrame(run_query(("""
                                SELECT fields.field_name as field, COALESCE(t.transcription_text, '') as value
                                    FROM transcription_fields fields LEFT JOIN transcription_files_text t
                                                 ON (fields.field_id = t.field_id and t.file_transcription_id = %(file_id)s)
                                    WHERE fields.transcription_source_id = %(source_id)s
                                            ORDER BY fields.sort_by
                                    """), {'source_id': source_id, 'file_id': file_id}))


def get_file_details_transcription(folder_id, file_id):
    rows = run_query(("WITH data AS ("
                        "         SELECT file_transcription_id, "
                        "             folder_transcription_id, file_name, dams_uan, "
                        "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(NOW(), created_at) as datediff "
                        "             FROM transcription_files "
                        "                 WHERE folder_transcription_id = %(folder_id)s AND folder_transcription_id IN (SELECT folder_transcription_id FROM transcription_folders)"
                        " UNION "
                        "         SELECT file_transcription_id,  "
                        "                folder_transcription_id, file_name, dams_uan, "
                        "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(created_at, NOW()) as datediff "
                        "             FROM transcription_files "
                        "                 WHERE folder_transcription_id = %(folder_id)s AND folder_transcription_id NOT IN (SELECT folder_transcription_id FROM transcription_folders)"
                        "             ORDER BY file_name"
                        "),"
                        "data2 AS (SELECT file_transcription_id, folder_transcription_id, file_name, dams_uan, created_at, datediff, "
                        "         lag(file_transcription_id,1) over (order by file_name) prev_id,"
                        "         lead(file_transcription_id,1) over (order by file_name) next_id "
                        " FROM data)"
                        " SELECT "
                        " file_transcription_id as file_id, "
                        "     folder_transcription_id, file_name, dams_uan, prev_id, next_id, created_at, datediff "
                        " FROM data2 WHERE file_transcription_id = %(file_id)s LIMIT 1"),
                        {'folder_id': folder_id, 'file_id': file_id})
    return rows[0]


def get_file_checks_transcription(file_id):
    return run_query(("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                          " ELSE check_info END AS check_info "
                          " FROM transcription_files_checks WHERE file_transcription_id = %(file_id)s"),
                         {'file_id': file_id})


def send_folder_to_dams(folder_id):
    """Mark a folder as delivered to DAMS and refresh its file/folder badges."""
    # Set as in the way to DAMS
    query_database_insert(
        ("UPDATE folders SET delivered_to_dams = 1 WHERE folder_id = %(folder_id)s"),
        {'folder_id': folder_id})

    # Del DAMS status badge, if exists
    query_database_insert(
            ("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'"),
                {'folder_id': folder_id})

    # Set as Ready for DAMS
    query_database_insert(
            ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text) "
             " VALUES (%(folder_id)s, 'dams_status', 'bg-secondary', 'Ready for DAMS')"),
                {'folder_id': folder_id})

    # Update post-proc
    query_database_insert(
            ("""
                INSERT INTO file_postprocessing
                    (file_id, post_results, post_step)
                (
                    SELECT file_id, 0 as post_results, 'ready_for_dams' as post_step
                    FROM (SELECT file_id FROM files WHERE folder_id = %(folder_id)s) a
                ) ON
                DUPLICATE KEY UPDATE
                post_results = 0
            """),
                {'folder_id': folder_id})

    # Update DAMS UAN
    query_database_insert(
            ("""
                UPDATE files f,
                (
                    SELECT f.file_id, d.dams_uan
                    FROM
                        dams_cdis_file_status_view_dpo d, files f, folders fold, projects p
                    WHERE
                        fold.folder_id = f.folder_id AND
                        fold.project_id = p.project_id AND
                        d.project_cd = p.dams_project_cd AND
                        d.file_name = CONCAT(f.file_name, '.tif') AND
                        f.folder_id =   %(folder_id)s
                ) d
                SET f.dams_uan = d.dams_uan WHERE f.file_id = d.file_id
            """),
                {'folder_id': folder_id})

    # Update in DAMS
    query_database_insert(
            ("""
                INSERT INTO file_postprocessing
                    (file_id, post_results, post_step)
                (
                    SELECT
                         file_id, 0 as post_results, 'in_dams' as post_step
                    FROM
                     (
                     SELECT file_id FROM files
                     WHERE folder_id = %(folder_id)s AND
                        dams_uan != '' AND dams_uan IS NOT NULL
                     ) a
                ) ON DUPLICATE KEY UPDATE post_results = 0
            """),
                {'folder_id': folder_id})

    no_files_ready = run_query(
        ("SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND dams_uan != '' AND dams_uan IS NOT NULL"),
        {'folder_id': folder_id})

    no_files_pending = run_query(
        ("SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND (dams_uan = '' OR dams_uan IS NULL)"),
        {'folder_id': folder_id})

    if no_files_ready[0]['no_files'] > 0 and no_files_pending[0]['no_files'] == 0:
        # Update in DAMS
        query_database_insert(
            ("UPDATE folders SET delivered_to_dams = 0 WHERE folder_id = %(folder_id)s"),
            {'folder_id': folder_id})
        query_database_insert(
            ("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'"),
            {'folder_id': folder_id})
        query_database_insert(
            ("""
                INSERT INTO folders_badges
                    (folder_id, badge_type, badge_css, badge_text) VALUES
                    (%(folder_id)s, 'dams_status', 'bg-success', 'Delivered to DAMS')
            """), {'folder_id': folder_id})


def mark_file_sensitive(file_id, sensitive_info, user_id):
    query_database_insert(
        ("INSERT INTO sensitive_contents (file_id, sensitive_contents, sensitive_info, user_id) "
         "VALUES (%(file_id)s, 1, %(sensitive_info)s, %(user_id)s) ON DUPLICATE KEY UPDATE sensitive_contents = 1"),
        {'file_id': file_id, 'sensitive_info': sensitive_info, 'user_id': user_id})
