"""Project read queries shared by the API."""

from osprey.db import run_query
from osprey.services import folders as folder_service


def get_project_row(project_alias):
    return run_query(
        ("SELECT "
         "project_id, "
         "project_title, "
         "project_alias, "
         "project_unit, "
         "project_status, "
         "project_description, "
         "project_type, "
         "project_method, "
         "project_manager, "
         "project_area, "
         "date_format(project_start, '%Y-%m-%d') AS project_start, "
         "CASE WHEN project_end IS NULL THEN NULL ELSE date_format(project_end, '%Y-%m-%d') END as project_end, "
         "project_notice, "
         "date_format(updated_at, '%Y-%m-%d') AS updated_at, "
         "transcription "
         "FROM projects "
         "WHERE project_alias = %(project_alias)s"),
        {'project_alias': project_alias},
    )


def enrich_project_details(project_row):
    """Attach folders, checks, stats, and reports to a project row dict."""
    project_id = project_row['project_id']
    transcription = project_row['transcription']
    project_row['folders'] = folder_service.list_for_project_api(project_id, transcription)
    project_checks = run_query(
        ("SELECT settings_value as project_check FROM projects_settings "
         " WHERE project_id = %(project_id)s AND project_setting = 'project_checks'"),
        {'project_id': project_id},
    )
    project_row['project_checks'] = ','.join(str(v['project_check']) for v in project_checks)
    project_postprocessing = run_query(
        ("SELECT settings_value as project_postprocessing FROM projects_settings "
         " WHERE project_id = %(project_id)s AND project_setting = 'project_postprocessing' ORDER BY table_id"),
        {'project_id': project_id},
    )
    project_row['project_postprocessing'] = ','.join(
        str(v['project_postprocessing']) for v in project_postprocessing
    )
    project_stats = run_query(
        ("SELECT collex_total, objects_digitized, images_taken "
         "FROM projects_stats WHERE project_id = %(project_id)s"),
        {'project_id': project_id},
    )
    project_row['project_stats'] = project_stats[0]
    project_row['reports'] = run_query(
        "SELECT report_id, report_title FROM data_reports WHERE project_id = %(project_id)s",
        {'project_id': project_id},
    )
    return project_row


def list_projects(section=None):
    if section not in ['MD', 'IS']:
        query = (
            " SELECT "
            " p.project_id, "
            " p.projects_order, "
            " p.project_unit, "
            " u.unit_fullname, "
            " p.project_alias, "
            " p.project_title, "
            " p.project_status, "
            " p.project_manager, "
            " date_format(p.project_start, '%Y-%m-%d') AS project_start, "
            " CASE WHEN p.project_end IS NULL THEN NULL ELSE date_format(p.project_end, '%Y-%m-%d') END AS project_end, "
            " p.objects_estimated,  "
            " ps.objects_digitized, "
            " p.images_estimated, "
            " p.transcription, "
            " ps.images_taken, "
            " ps.images_public "
            " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id), si_units u "
            " WHERE p.project_unit = u.unit_id AND p.skip_project = 0 "
            " GROUP BY "
            "        p.project_id, p.project_title, p.project_unit, u.unit_fullname, p.project_status, p.project_description, "
            "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
            "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
            " ORDER BY p.projects_order DESC"
        )
        return run_query(query)
    query = (
        " SELECT "
        " p.project_id, "
        " p.projects_order, "
        " p.project_unit, "
        " u.unit_fullname, "
        " p.project_alias, "
        " p.project_title, "
        " p.project_status, "
        " p.project_manager, "
        " date_format(p.project_start, '%Y-%m-%d') AS project_start, "
        " CASE WHEN p.project_end IS NULL THEN NULL ELSE date_format(p.project_end, '%Y-%m-%d') END AS project_end, "
        " p.objects_estimated,  "
        " ps.objects_digitized, "
        " p.images_estimated, "
        " p.transcription, "
        " ps.images_taken, "
        " ps.images_public "
        " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id), si_units u "
        " WHERE p.project_unit = u.unit_id AND p.skip_project = 0 AND p.project_section = %(section)s "
        " GROUP BY "
        "        p.project_id, p.project_title, p.project_unit, p.project_status, u.unit_fullname, p.project_description, "
        "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
        "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
        " ORDER BY p.projects_order DESC"
    )
    return run_query(query, {'section': section})


def list_project_files(project_alias):
    return run_query(
        ("SELECT f.file_id, f.uid, f.file_name, f.folder_id FROM files f WHERE f.folder_id in "
         " (SELECT folder_id FROM folders WHERE project_id in "
         "(SELECT project_id from projects WHERE project_alias = %(project_alias)s)) ORDER BY f.file_name"),
        {'project_alias': project_alias},
    )
