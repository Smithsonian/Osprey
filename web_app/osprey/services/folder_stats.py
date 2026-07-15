"""Recalculate folder and project stats (shared by worker and bulk API)."""

from logger import api_logger as logger
from osprey.db import query_database_insert, run_query
from osprey.services.file_checks import assert_safe_sql_expression


def recalculate_folder_stats(project_id, folder_id, transcription):
    """Recalculate stats for a single folder. Returns a summary dict.

    Raises ValueError only for unexpected programming errors; SQL validation
    errors for project-level expressions live in recalculate_project_stats.
    """
    if transcription == 1:
        folder_table = "transcription_folders"
        fid = "folder_uid"
    else:
        folder_table = "folders"
        fid = "folder_id"

    # Clear badges
    run_query(
        f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'no_files'",
        {'folder_id': folder_id},
    )
    run_query(
        f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'error_files'",
        {'folder_id': folder_id},
    )
    run_query(
        f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'verification'",
        {'folder_id': folder_id},
    )
    run_query(
        f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_error'",
        {'folder_id': folder_id},
    )

    # Badge of no_files
    if transcription == 1:
        no_files = run_query(
            "SELECT COUNT(*) AS no_files FROM transcription_files WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id},
        )
    else:
        no_files = run_query(
            "SELECT COUNT(*) AS no_files FROM files WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id},
        )
    no_folder_files = None
    if no_files[0]['no_files'] > 0:
        if no_files[0]['no_files'] == 1:
            no_folder_files = "1 file"
        else:
            no_folder_files = "{} files".format(no_files[0]['no_files'])
        query = (
            f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) "
            "VALUES (%(folder_id)s, 'no_files', 'bg-primary', %(no_files)s, CURRENT_TIMESTAMP) "
            "ON DUPLICATE KEY UPDATE badge_text = %(no_files)s, badge_css = 'bg-primary', updated_at = CURRENT_TIMESTAMP"
        )
        res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files})
        logger.info("folder_stats: no_files badge|{}|{}".format(folder_id, res))

    # Badge of error files
    if transcription == 1:
        query = (
            "UPDATE transcription_folders f SET f.file_errors = 0 "
            "where folder_transcription_id = %(folder_id)s"
        )
    else:
        query = "UPDATE folders f SET f.file_errors = 0 where folder_id = %(folder_id)s"
    res = query_database_insert(query, {'folder_id': folder_id})
    logger.info("folder_stats: clear file_errors|{}|{}".format(folder_id, res))

    if transcription == 1:
        query = (
            "WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_transcription_id) > 0 THEN 1 ELSE 0 END AS no_files, "
            "%(folder_id)s as folder_transcription_id "
            " FROM transcription_files_checks c, transcription_files f "
            " WHERE f.folder_transcription_id = %(folder_id)s "
            " AND f.file_transcription_id = c.file_transcription_id AND c.check_results = 1)"
            " UPDATE transcription_folders f, data d SET f.file_errors = d.no_files "
            "WHERE f.folder_transcription_id = d.folder_transcription_id"
        )
    else:
        query = (
            "WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_id) > 0 THEN 1 ELSE 0 END AS no_files, "
            "%(folder_id)s as folder_id FROM files_checks c, files f"
            " WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 1)"
            " UPDATE folders f, data d SET f.file_errors = d.no_files "
            "WHERE f.folder_id = d.folder_id"
        )
    res = query_database_insert(query, {'folder_id': folder_id})
    logger.info("folder_stats: set file_errors|{}|{}".format(folder_id, res))

    if transcription == 1:
        file_errors_row = run_query(
            "SELECT file_errors FROM transcription_folders WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id},
        )
    else:
        file_errors_row = run_query(
            "SELECT file_errors FROM folders WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id},
        )
    if file_errors_row[0]['file_errors'] == 1:
        if transcription == 1:
            query = (
                "INSERT INTO folders_badges (folder_uid, badge_type, badge_css, badge_text, updated_at) "
                " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) "
                "ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP"
            )
        else:
            query = (
                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) "
                "ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP"
            )
        res = query_database_insert(
            query, {'folder_id': folder_id, 'no_files': no_folder_files},
        )
        logger.info("folder_stats: error_files badge|{}|{}".format(folder_id, res))

    # Update updated_at datetime
    if transcription == 1:
        query = (
            "UPDATE transcription_folders SET updated_at = NOW() "
            "WHERE folder_transcription_id = %(folder_id)s"
        )
    else:
        query = "UPDATE folders SET updated_at = NOW() WHERE folder_id = %(folder_id)s"
    res = query_database_insert(query, {'folder_id': folder_id})
    logger.info("folder_stats: updated_at|{}|{}".format(folder_id, res))

    # Check for other error badges
    query_other_errors = run_query(
        f"SELECT count(*) as no_badges from folders_badges where {fid} = %(folder_id)s AND badge_css = 'bg-danger'",
        {'folder_id': folder_id},
    )[0]
    if query_other_errors['no_badges'] > 0:
        if transcription == 1:
            query = (
                "UPDATE transcription_folders f SET f.file_errors = 1 "
                "where folder_transcription_id = %(folder_id)s"
            )
        else:
            query = "UPDATE folders f SET f.file_errors = 1 where folder_id = %(folder_id)s"
        query_database_insert(query, {'folder_id': folder_id})

    # Calculate counts for folder
    if transcription == 1:
        no_files = run_query(
            "SELECT count(*) as no_files FROM transcription_files WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id},
        )[0]
        query_database_insert(
            "UPDATE transcription_folders SET no_files_total = %(no_files)s "
            "WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id, 'no_files': no_files['no_files']},
        )
        no_error_files = run_query(
            "SELECT count(distinct f.file_transcription_id) as no_files "
            "FROM transcription_files f, transcription_files_checks fc "
            "WHERE f.folder_transcription_id = %(folder_id)s "
            "and f.file_transcription_id = fc.file_transcription_id AND fc.check_results = 1",
            {'folder_id': folder_id},
        )[0]
        query_database_insert(
            "UPDATE transcription_folders SET no_files_errors = %(no_files)s "
            "WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id, 'no_files': no_error_files['no_files']},
        )
        no_ok_files = run_query(
            """
            with no_checks as (
                SELECT count(*) as no_checks FROM projects_settings
                WHERE project_id = %(project_id)s and project_setting = 'project_checks'
            ),
            no_files as (
                SELECT f.file_transcription_id, count(*) as no_files
                FROM transcription_files f, transcription_files_checks fc
                WHERE f.folder_transcription_id = %(folder_id)s
                  and f.file_transcription_id = fc.file_transcription_id
                  and fc.check_results = 0
                group by f.file_transcription_id
            )
            select count(no_files.file_transcription_id) as ok_files
            from no_files, no_checks
            where no_files.no_files = no_checks.no_checks
            """,
            {'project_id': project_id, 'folder_id': folder_id},
        )[0]
        query_database_insert(
            "UPDATE transcription_folders SET no_files_ok = %(no_files)s "
            "WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id, 'no_files': no_ok_files['ok_files']},
        )
        no_checks = run_query(
            "SELECT count(*) as no_checks FROM projects_settings "
            "WHERE project_id = %(project_id)s and project_setting = 'project_checks'",
            {'project_id': project_id},
        )[0]
        total_checks = int(no_checks['no_checks']) * int(no_files['no_files'])
        no_pending = run_query(
            "SELECT count(*) as no_files from transcription_files_checks "
            "where file_transcription_id in ("
            "  select file_transcription_id from transcription_files "
            "  where folder_transcription_id = %(folder_id)s"
            ") and (check_results = 0 or check_results = 1)",
            {'folder_id': folder_id},
        )[0]
    else:
        no_files = run_query(
            "SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id},
        )[0]
        query_database_insert(
            f"UPDATE {folder_table} SET no_files_total = %(no_files)s WHERE {fid}= %(folder_id)s",
            {'folder_id': folder_id, 'no_files': no_files['no_files']},
        )
        no_error_files = run_query(
            "SELECT count(distinct f.file_id) as no_files FROM files f, files_checks fc "
            "WHERE f.folder_id = %(folder_id)s and f.file_id = fc.file_id and fc.check_results = 1",
            {'folder_id': folder_id},
        )[0]
        query_database_insert(
            "UPDATE folders SET no_files_errors = %(no_files)s WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id, 'no_files': no_error_files['no_files']},
        )
        no_ok_files = run_query(
            """
            with no_checks as (
                SELECT count(*) as no_checks FROM projects_settings
                WHERE project_id = %(project_id)s and project_setting = 'project_checks'
            ),
            no_files as (
                SELECT f.file_id, count(*) as no_files FROM files f, files_checks fc
                WHERE f.folder_id = %(folder_id)s and f.file_id = fc.file_id and fc.check_results = 0
                group by f.file_id
            )
            select count(no_files.file_id) as ok_files
            from no_files, no_checks
            where no_files.no_files = no_checks.no_checks
            """,
            {'project_id': project_id, 'folder_id': folder_id},
        )[0]
        query_database_insert(
            "UPDATE folders SET no_files_ok = %(no_files)s WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id, 'no_files': no_ok_files['ok_files']},
        )
        no_checks = run_query(
            "SELECT count(*) as no_checks FROM projects_settings "
            "WHERE project_id = %(project_id)s and project_setting = 'project_checks'",
            {'project_id': project_id},
        )[0]
        total_checks = int(no_checks['no_checks']) * int(no_files['no_files'])
        no_pending = run_query(
            "SELECT count(*) as no_files from files_checks "
            "where file_id in (select file_id from files where folder_id = %(folder_id)s) "
            "and (check_results = 0 or check_results = 1)",
            {'folder_id': folder_id},
        )[0]

    # Verify all checks were completed
    logger.info("folder_stats: checks {}/{}".format(total_checks, no_pending['no_files']))
    if int(total_checks) != int(no_pending['no_files']):
        if transcription == 1:
            query = (
                "UPDATE transcription_folders SET status = 1, error_info = %(value)s "
                "WHERE folder_transcription_id = %(folder_id)s"
            )
        else:
            query = (
                "UPDATE folders SET status = 1, error_info = %(value)s "
                "WHERE folder_id = %(folder_id)s"
            )
        res = query_database_insert(
            query,
            {
                'value': "File checks totals don't match: {}/{}/{}".format(
                    total_checks, no_pending['no_files'], no_files['no_files'],
                ),
                'folder_id': folder_id,
            },
        )
        logger.info("folder_stats: checks mismatch|{}|{}".format(folder_id, res))
        run_query(
            f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_error'",
            {'folder_id': folder_id},
        )
        if transcription == 1:
            query = (
                "INSERT INTO folders_badges (folder_uid, badge_type, badge_css, badge_text, updated_at) "
                " VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) "
                "ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
                " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP"
            )
        else:
            query = (
                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                " VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) "
                "ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
                " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP"
            )
        res = query_database_insert(query, {'folder_id': folder_id, 'msg': "System Error"})
        logger.info("folder_stats: system error badge|{}|{}".format(folder_id, res))

    if transcription == 1:
        summary = run_query(
            "SELECT folder_transcription_id as folder_id, folder, "
            "no_files_total, no_files_errors, no_files_ok, file_errors "
            "FROM transcription_folders WHERE folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id},
        )[0]
    else:
        summary = run_query(
            "SELECT folder_id, project_folder as folder, "
            "no_files_total, no_files_errors, no_files_ok, file_errors "
            "FROM folders WHERE folder_id = %(folder_id)s",
            {'folder_id': folder_id},
        )[0]
    return {
        'folder_id': summary['folder_id'],
        'folder': summary['folder'],
        'no_files_total': summary['no_files_total'],
        'no_files_errors': summary['no_files_errors'],
        'no_files_ok': summary['no_files_ok'],
        'file_errors': summary['file_errors'],
    }


def recalculate_project_stats(project_id, transcription):
    """Roll up folder totals into projects_stats.

    Raises ValueError with message 'Invalid project_object_query' or
    'Invalid other_stat_calc' when a stored expression fails validation.
    """
    # Update images_taken count
    if transcription == 1:
        query = (
            "with data as "
            "  (select fol.project_id, count(f.file_name) as no_files "
            "          from transcription_files f, transcription_folders fol "
            "          where fol.project_id = %(project_id)s "
            "            and fol.folder_transcription_id = f.folder_transcription_id)"
            "UPDATE projects_stats p, data SET p.images_taken = data.no_files "
            "where p.project_id = data.project_id"
        )
    else:
        query = (
            "with data as "
            "  (select fol.project_id, count(f.file_name) as no_files "
            "          from files f, folders fol "
            "          where fol.project_id = %(project_id)s and fol.folder_id = f.folder_id)"
            "UPDATE projects_stats p, data SET p.images_taken = data.no_files "
            "where p.project_id = data.project_id"
        )
    res = query_database_insert(query, {'project_id': project_id})
    logger.info("project_stats: images_taken|{}|{}".format(project_id, res))

    # objects_digitized
    query_obj = run_query(
        "SELECT project_object_query FROM projects WHERE project_id = %(project_id)s",
        {'project_id': project_id},
    )[0]
    try:
        object_expr = assert_safe_sql_expression(query_obj['project_object_query'])
    except ValueError as err:
        logger.error(
            "Unsafe project_object_query for project_id=%s: %s",
            project_id, err,
        )
        raise ValueError('Invalid project_object_query') from err
    if transcription == 1:
        query = (
            "with data as "
            "  (select fol.project_id, {} as no_objects"
            "          from transcription_files f, transcription_folders fol "
            "          where fol.project_id = %(project_id)s "
            "            and fol.folder_transcription_id = f.folder_transcription_id)"
            " UPDATE projects_stats p, data SET p.objects_digitized = data.no_objects "
            "where p.project_id = data.project_id".format(object_expr)
        )
    else:
        query = (
            "with data as "
            "  (select fol.project_id, {} as no_objects"
            "          from files f, folders fol "
            "          where fol.project_id = %(project_id)s and fol.folder_id = f.folder_id)"
            " UPDATE projects_stats p, data SET p.objects_digitized = data.no_objects "
            "where p.project_id = data.project_id".format(object_expr)
        )
    res = query_database_insert(query, {'project_id': project_id})
    logger.info("project_stats: objects_digitized|{}|{}".format(project_id, res))

    # other_stat
    query_stat_other = run_query(
        "SELECT other_stat_calc FROM projects_stats WHERE project_id = %(project_id)s",
        {'project_id': project_id},
    )
    if query_stat_other[0]['other_stat_calc'] is not None:
        try:
            other_expr = assert_safe_sql_expression(query_stat_other[0]['other_stat_calc'])
        except ValueError as err:
            logger.error(
                "Unsafe other_stat_calc for project_id=%s: %s",
                project_id, err,
            )
            raise ValueError('Invalid other_stat_calc') from err
        if transcription == 1:
            query = (
                "with data as "
                "  (select fol.project_id, {} as no_objects"
                "          from transcription_files f, transcription_folders fol "
                "          where fol.project_id = %(project_id)s "
                "            and fol.folder_transcription_id = f.folder_transcription_id)"
                " UPDATE projects_stats p, data SET p.other_stat = data.no_objects "
                "where p.project_id = data.project_id".format(other_expr)
            )
        else:
            query = (
                "with data as "
                "  (select fol.project_id, {} as no_objects"
                "          from files f, folders fol "
                "          where fol.project_id = %(project_id)s and fol.folder_id = f.folder_id)"
                " UPDATE projects_stats p, data SET p.other_stat = data.no_objects "
                "where p.project_id = data.project_id".format(other_expr)
            )
        res = query_database_insert(query, {'project_id': project_id})
        logger.info("project_stats: other_stat|{}|{}".format(project_id, res))

    # Roll up folder file counts into projects_stats
    if transcription == 1:
        folders_table = "transcription_folders"
    else:
        folders_table = "folders"
    query = (
        f"""WITH folders_q AS (
                SELECT project_id,
                        SUM(no_files_total)  AS images_taken,
                        SUM(no_files_errors) AS project_err,
                        SUM(no_files_ok)     AS project_ok
                FROM {folders_table}
                WHERE project_id = %(project_id)s
                GROUP BY project_id
                )
                UPDATE projects_stats AS s
                JOIN folders_q AS fol
                ON fol.project_id = s.project_id
                SET
                s.images_taken = fol.images_taken,
                s.project_err  = fol.project_err,
                s.project_ok   = fol.project_ok
                WHERE s.project_id = %(project_id)s
        """
    )
    res = query_database_insert(query, {'project_id': project_id})
    logger.info("project_stats: rollup|{}|{}".format(project_id, res))
