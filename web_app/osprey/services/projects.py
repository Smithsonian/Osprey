"""Project read queries shared by the API."""

from logger import logger
from osprey.db import query_database_insert, run_query
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
         "transcription, "
         "qc_status "
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


def get_project_id_row(project_alias):
    return run_query(
        "SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
        {'project_alias': project_alias})


def get_project_for_edit(project_alias):
    rows = run_query(("SELECT p.project_id, p.project_alias, "
                          " p.project_title, p.project_alias, p.project_start, p.project_end, "
                          " p.project_unit, p.project_section, p.project_status, NULL as project_url, "
                          " COALESCE(p.project_description, '') as project_description, "
                          " COALESCE(s.collex_to_digitize, 0) AS collex_to_digitize "
                          " FROM projects p LEFT JOIN projects_stats s "
                          "     ON (p.project_id = s.project_id) "
                          " WHERE p.project_alias = %(project_alias)s"),
                         {'project_alias': project_alias})
    return rows[0] if rows else None


def count_project_admin(username, project_alias):
    """Return the COUNT(*) row for whether `username` is a qc_projects user on `project_alias`.

    Always returns exactly one row (a COUNT(*) query never returns zero rows) --
    check result[0]['no_results'] == 0, not len(result) == 0.
    """
    return run_query(("SELECT count(*) as no_results "
                            "    FROM users u, qc_projects qp, projects p "
                            "    WHERE u.username = %(username)s "
                            "        AND p.project_alias = %(project_alias)s "
                            "        AND qp.project_id = p.project_id "
                            "        AND u.user_id = qp.user_id"),
                           {'username': username, 'project_alias': project_alias})


def create_project(p_title, p_unit, p_alias, p_desc, p_coordurl, p_area, p_md, p_method,
                    p_manager, p_prod, p_storage, p_start, p_noobjects, creator_user_id, file_checks):
    """Insert a new project, its stats row, qc_projects assignments, and default file checks.

    `file_checks` is a dict of raw form values (e.g. {'raw_pair': '1'}); a check is
    enabled when its value is the string "1", matching the original form handling.
    """
    project_id = query_database_insert(("INSERT INTO projects  "
                              "   (project_title, project_unit, project_alias, project_description, "
                              "    project_coordurl, project_area, project_section, project_method, "
                              "    project_manager, project_status, project_type, project_datastorage,"
                              "    project_start, projects_order, stats_estimated) "
                              "  (SELECT "
                              "            %(p_title)s, %(p_unit)s, %(p_alias)s, %(p_desc)s, "
                              "            %(p_coordurl)s, %(p_area)s, %(p_md)s, %(p_method)s, "
                              "            %(p_manager)s, 'Ongoing', %(p_prod)s, %(p_storage)s, "
                              "            %(p_start)s, max(projects_order) + 1, 0 FROM projects)"),
                             {'p_title': p_title, 'p_unit': p_unit, 'p_alias': p_alias, 'p_desc': p_desc,
                              'p_coordurl': p_coordurl, 'p_area': p_area, 'p_md': p_md,
                              'p_method': p_method, 'p_manager': p_manager,
                              'p_prod': p_prod, 'p_storage': p_storage, 'p_start': p_start
                              }, return_res=True)
    logger.debug("PROJECT ID: {}".format(project_id))
    query_database_insert(
        ("INSERT INTO projects_stats (project_id, collex_total, collex_to_digitize) "
         "VALUES (%(project_id)s, %(collex_total)s, %(collex_total)s)"),
        {'project_id': project_id, 'collex_total': int(p_noobjects)})
    query_database_insert(
        "INSERT INTO qc_projects (project_id, user_id) VALUES (%(project_id)s, %(user_id)s)",
        {'project_id': project_id, 'user_id': creator_user_id})
    if creator_user_id != '101':
        query_database_insert(
            "INSERT INTO qc_projects (project_id, user_id) VALUES (%(project_id)s, %(user_id)s)",
            {'project_id': project_id, 'user_id': '101'})

    fcheck_query = ("INSERT INTO projects_settings (project_id, project_setting, settings_value) "
                     "VALUES (%(project_id)s, 'project_checks', %(value)s)")
    for value in ('unique_file', 'tifpages', 'md5'):
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': value})
    if file_checks.get('raw_pair') == "1":
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'raw_pair'})
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'md5_raw'})
    if file_checks.get('tif_compression') == "1":
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'tif_compression'})
    if file_checks.get('magick') == "1":
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'magick'})
    if file_checks.get('jhove') == "1":
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'jhove'})
    if file_checks.get('sequence') == "1":
        query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'sequence'})
    return project_id


def update_project(project_alias, project_id, p_title, p_status, p_start, p_desc, p_end, p_noobjects):
    query_database_insert(("UPDATE projects SET "
                              "   project_title = %(p_title)s, "
                              "   project_status = %(p_status)s, "
                              "   project_start = CAST(%(p_start)s AS date) "
                              " WHERE project_alias = %(project_alias)s"),
                             {'p_title': p_title,
                              'p_status': p_status,
                              'p_start': p_start,
                              'project_alias': project_alias})
    if p_desc != '':
        query_database_insert(("UPDATE projects SET "
                                  "   project_description = %(p_desc)s "
                                  " WHERE project_alias = %(project_alias)s"),
                                 {'p_desc': p_desc,
                                  'project_alias': project_alias})
    if p_end != 'None':
        query_database_insert(("UPDATE projects SET "
                                  "   project_end = CAST(%(p_end)s AS date) "
                                  " WHERE project_alias = %(project_alias)s "),
                                 {'p_end': p_end,
                                  'project_alias': project_alias})
    if p_noobjects != '0':
        query_database_insert(("UPDATE projects_stats SET "
                                  "   collex_to_digitize = %(p_noobjects)s, "
                                  "   collex_ready = %(p_noobjects)s "
                                  " WHERE project_id = %(project_id)s "),
                                 {'project_id': project_id,
                                  'p_noobjects': p_noobjects})


def list_informatics_projects():
    inf_section_query = (" SELECT "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\">', p.project_unit, '</abbr>') as project_unit, "
                     " CONCAT('<strong><a href=\"/infprojects/', p.proj_id, '\">', p.project_title, '</a></strong><br>', p.summary) as project_title, "
                     " p.project_status, "
                     " CASE WHEN p.github_link IS NULL THEN 'NA' ELSE "
                     "       CONCAT('<a href=\"', p.github_link, '\" title=\"Link to code repository of ', p.project_title, ' in Github\">Repository</a>') END as github_link, "
                     " CASE "
                     "      WHEN p.project_end IS NULL THEN CONCAT(date_format(p.project_start, '%b %Y'), ' -') "
                     "      WHEN date_format(p.project_start, '%b %Y') = date_format(p.project_end, '%b %Y') THEN date_format(p.project_start, '%b %Y') "
                     "      ELSE CONCAT(date_format(p.project_start, '%b %Y'), ' - ', date_format(p.project_end, '%b %Y')) END "
                     "         as project_dates, "
                     " CASE WHEN p.records = 0 THEN 'NA' ELSE "
                     " (CASE WHEN p.records_estimated IS True THEN CONCAT(coalesce(format(p.records, 0), 0), '*') ELSE "
                     "      coalesce(format(p.records, 0), 0) END) END as records, "
                     " CASE WHEN p.info_link IS NULL THEN 'NA' ELSE p.info_link END AS info_link "
                     " FROM projects_informatics p LEFT JOIN si_units u ON (p.project_unit = u.unit_id) "
                     " ORDER BY p.project_start DESC, p.project_end DESC")
    return run_query(inf_section_query)


def get_informatics_project(proj_id):
    return run_query("SELECT * FROM projects_informatics WHERE proj_id = %(proj_id)s", {'proj_id': proj_id})[0]


def list_si_units():
    return run_query("SELECT * FROM si_units")


def upsert_informatics_project(proj_edit, proj_id, project_title, project_unit, summary, records, pm,
                                project_status, github_link, info_link, project_start, project_end):
    """Create or update an informatics project."""
    if github_link in ("", "None"):
        github_link = None
    if info_link in ("", "None"):
        info_link = None
    if project_end == "":
        project_end = None

    params = {
        'project_title': project_title,
        'project_unit': project_unit,
        'summary': summary,
        'records': records,
        'pm': pm,
        'project_status': project_status,
        'github_link': github_link,
        'info_link': info_link,
        'project_start': project_start,
        'project_end': project_end,
        'proj_id': proj_id,
    }

    if proj_edit == "0":
        query_database_insert(
            ("INSERT INTO projects_informatics "
             "     (proj_id, project_title, project_unit, summary, records, pm, project_status, github_link, info_link, project_start, project_end) VALUES "
             "     (%(proj_id)s, %(project_title)s, %(project_unit)s, %(summary)s, %(records)s, %(pm)s, %(project_status)s, %(github_link)s, %(info_link)s, %(project_start)s, %(project_end)s)"),
            params, return_res=True)
    elif proj_edit == "1":
        query_database_insert(
            ("UPDATE projects_informatics SET "
             "     project_title = %(project_title)s, "
             "     project_unit = %(project_unit)s, "
             "     summary = %(summary)s, "
             "     records = %(records)s, "
             "     pm = %(pm)s, "
             "     project_status = %(project_status)s, "
             "     github_link = %(github_link)s, "
             "     info_link = %(info_link)s, "
             "     project_start = %(project_start)s, "
             "     project_end = %(project_end)s "
             " WHERE proj_id = %(proj_id)s"),
            params, return_res=False)


def get_project_links(project_id):
    return run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                               {'project_id': project_id})


def add_project_link(project_id, link_type, link_title, link_url):
    query_database_insert(("INSERT INTO projects_links "
                              "   (project_id, link_type, link_title, url) "
                              "  (SELECT %(project_id)s, %(link_type)s, %(link_title)s, %(url)s)"),
                             {'project_id': project_id,
                              'link_type': link_type,
                              'link_title': link_title,
                              'url': link_url
                              })
