#!flask/bin/python
#
# API
#
# Import flask
from flask import Flask
from flask import Blueprint
import os 
import shutil
from flask import jsonify
from flask import request
from uuid import UUID
import json
import pandas as pd

# MySQL
import pymysql

from osprey_common import *

# Import caching
from cache import cache

# Logging
from logger import logger

import settings


################################
# Functions
################################
def run_query(query, parameters=None, return_val=True, cur=None):
    logger.info("parameters: {}".format(parameters))
    logger.info("query: {}".format(query))
    # Run query
    try:
        if parameters is None:
            results = cur.execute(query)
        else:
            results = cur.execute(query, parameters)
    except pymysql.Error as error:
        logger.error("API Error {}".format(error))
        return jsonify({'error': 'API error'}), 500
    if return_val:
        data = cur.fetchall()
        logger.info("No of results: ".format(len(data)))
        return data
    else:
        return True


def validate_api_key(api_key, cur=None):
    logger.info("api_key: {}".format(api_key))
    try:
        api_key_check = UUID(api_key)
    except ValueError:
        logger.error("Invalid UUID: {}".format(api_key))
        return jsonify({'error': "Invalid UUID: {}".format(api_key)}), 400
    # Run query
    query = ("SELECT api_key from api_keys WHERE api_key = %(api_key)s")
    parameters = {'api_key': api_key}
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    result = cur.execute(query, parameters)
    data = cur.fetchall()
    if len(data) == 1:
        if data[0]['api_key'] == api_key:
            return True
        else:
            return False
    else:
        return False


@cache.memoize()
def check_file_id(file_id=None, cur=None):
    if file_id is None:
        return False, False
    if cur is None:
        return False, False
    else:
        try:
            file_id = int(file_id)
            file_id_type = "int"
        except ValueError:
            try:
                file_uid = UUID(file_id, version=4)
                file_id_type = "uuid"
            except ValueError:
                return False, False

    if file_id_type == "uuid":
        file_id = run_query("SELECT file_id FROM files WHERE uid = %(uid)s", {'uid': file_uid}, cur=cur)
        if len(file_id) == 0:
            return False, False
        else:
            return file_id[0]['file_id'], file_uid
    else:
        file_uid = run_query("SELECT uid FROM files WHERE file_id = %(file_id)s", {'file_id': file_id}, cur=cur)
        if len(file_uid) == 0:
            return False, False
        else:
            return file_id, file_uid[0]['uid']


def query_database_insert(query, parameters, return_res=False, cur=None):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    # Run query
    data = False
    try:
        results = cur.execute(query, parameters)
    except Exception as error:
        logger.error(error)
        return jsonify({'error': 'API Error'}), 500
    data = cur.fetchall()
    logger.info("No of results: ".format(len(data)))
    if len(data) == 0:
        data = False
    return data


def query_database_insert_multi(query, parameters, return_res=False, cur=None):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    # Run query
    data = False
    try:
        results = cur.executemany(query, parameters)
    except Exception as error:
        logger.error("Error_insert_multi: {}".format(error))
        return False
    data = cur.fetchall()
    logger.info("No of results: ".format(len(data)))
    if len(data) == 0:
        data = False
    return data


###################################
# Osprey API
###################################
osprey_api = Blueprint('osprey_api', __name__)
@cache.memoize()
@osprey_api.route('/api/projects/', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_get_projects():
    """Get the list of projects."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logger.error(e)
        return jsonify({'error': 'API error'}), 500

    # For post use request.form.get("variable")
    section = request.form.get("section")
    # logger.info("VAL: {}".format(val))
    if section not in ['MD', 'IS']:
        query = (" SELECT "
                 " p.project_id, "
                 " p.projects_order, "
                 " p.project_unit, "
                 " u.unit_fullname, "
                 " p.project_alias, "
                 " p.project_title, "
                 " p.project_status, "
                 " p.project_manager, "
                 " date_format(p.project_start, '%Y-%b-%d') AS project_start, "
                 " CASE WHEN p.project_end IS NULL THEN NULL ELSE date_format(p.project_end, '%Y-%b-%d') END AS project_end, "
                 " p.objects_estimated,  "
                 " ps.objects_digitized, "
                 " p.images_estimated, "
                 " ps.images_taken, "
                 " ps.images_public "
                 " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id), si_units u "
                 " WHERE p.project_unit = u.unit_id AND p.skip_project = 0 "
                 " GROUP BY "
                 "        p.project_id, p.project_title, p.project_unit, u.unit_fullname, p.project_status, p.project_description, "
                 "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
                 "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
                 " ORDER BY p.projects_order DESC")
        projects_data = run_query(query, cur=cur)
    else:
        query = (" SELECT "
                 " p.project_id, "
                 " p.projects_order, "
                 " p.project_unit, "
                 " u.unit_fullname, "
                 " p.project_alias, "
                 " p.project_title, "
                 " p.project_status, "
                 " p.project_manager, "
                 " date_format(p.project_start, '%%Y-%%b-%%d') AS project_start, "
                 " CASE WHEN p.project_end IS NULL THEN NULL ELSE date_format(p.project_end, '%%Y-%%b-%%d') END AS project_end, "
                 " p.objects_estimated,  "
                 " ps.objects_digitized, "
                 " p.images_estimated, "
                 " ps.images_taken, "
                 " ps.images_public "
                 " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id), si_units u "
                 " WHERE p.project_unit = u.unit_id AND p.skip_project = 0 AND p.project_section = %(section)s "
                 " GROUP BY "
                 "        p.project_id, p.project_title, p.project_unit, p.project_status, u.unit_fullname, p.project_description, "
                 "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
                 "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
                 " ORDER BY p.projects_order DESC")
        projects_data = run_query(query, {'section': section}, cur=cur)
    last_update = run_query("SELECT date_format(MAX(updated_at), '%d-%b-%Y') AS updated_at FROM projects_stats", cur=cur)
    data = ({"projects": projects_data, "last_update": last_update[0]['updated_at']})
    # For admin
    api_key = request.form.get("api_key")
    logger.info("api_key: {}".format(api_key))
    if api_key is not None:
        if validate_api_key(api_key, cur=cur):
            query = (" SELECT * FROM qc_settings WHERE project_id = %(project_id)s")
            projects_data = run_query(query, {'section': section}, cur=cur)
    cur.close()
    conn.close()
    return jsonify(data)


@cache.memoize()
@osprey_api.route('/api/projects/<project_alias>', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_get_project_details(project_alias=None):
    """Get the details of a project by specifying the project_alias."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logger.error(e)
        return jsonify({'error': 'API error'}), 500

    api_key = request.form.get("api_key")
    logger.info("api_key: {}".format(api_key))
    if api_key is None or validate_api_key(api_key, cur=cur) is False:
        data = run_query(("SELECT "
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
                               "date_format(project_start, '%%y-%%m-%%d') AS project_start, "
                               "CASE WHEN project_end IS NULL THEN NULL ELSE date_format(project_end, '%%y-%%m-%%d') END as project_end, "
                               "project_notice, "
                               "cast(updated_at as DATE) AS updated_at "
                               "FROM projects "
                               " WHERE project_alias = %(project_alias)s"),
                              {'project_alias': project_alias}, cur=cur)
    else:
        data = run_query(("SELECT "
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
                               "project_datastorage, "
                               "date_format(project_start, '%%y-%%m-%%d') AS project_start, "
                               "CASE WHEN project_end IS NULL THEN NULL ELSE date_format(project_end, '%%y-%%m-%%d') END as project_end, "
                               "project_notice, "
                               "cast(updated_at AS DATE) as updated_at "
                               "FROM projects WHERE project_alias = %(project_alias)s"),
                              {'project_alias': project_alias}, cur=cur)
    if data is None:
        return jsonify({'error': 'Project does not exists'}), 401
    else:
        if api_key is None or validate_api_key(api_key, cur=cur) is False:
            folders = run_query(("SELECT "
                                      "folder_id, project_id, project_folder as folder, status, "
                                      "notes, error_info, date_format(date, '%%y-%%m-%%d') as capture_date, "
                                      "no_files, file_errors "
                                      "FROM folders WHERE project_id = %(project_id)s"),
                                     {'project_id': data[0]['project_id']}, cur=cur)
        else:
            folders = run_query(("SELECT "
                                      "f.folder_id, f.project_id, f.project_folder as folder, "
                                      "f.folder_path, f.status, f.notes, "
                                      "f.error_info, date_format(f.date, '%%y-%%m-%%d') as capture_date, "
                                      "f.no_files, f.file_errors, "
                                      " CASE WHEN f.delivered_to_dams = 1 THEN 0 ELSE 9 END as delivered_to_dams, "
                                      " COALESCE(CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                              " WHEN q.qc_status = 1 THEN 'QC Failed' "
                                              " WHEN q.qc_status = 9 THEN 'QC Pending' END, 'QC Pending') as qc_status,"
                                      " GROUP_CONCAT(b.badge_text) as badges"
                                      " FROM folders f LEFT JOIN qc_folders q ON (f.folder_id = q.folder_id)"
                                      "     LEFT JOIN folders_badges b ON (f.folder_id = b.folder_id) "
                                      " WHERE project_id = %(project_id)s"
                                      " GROUP BY f.folder_id, f.project_id, f.project_folder, f.folder_path, "
                                      "      f.status, f.notes, f.error_info, f.date, f.no_files,"
                                      "      f.file_errors, q.qc_status"),
                                     {'project_id': data[0]['project_id']}, cur=cur)
        project_checks = run_query(("SELECT settings_value as project_check FROM projects_settings "
                                         " WHERE project_id = %(project_id)s AND project_setting = 'project_checks'"),
                                        {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['project_checks'] = ','.join(str(v['project_check']) for v in project_checks)
        project_postprocessing = run_query(("SELECT settings_value as project_postprocessing FROM projects_settings "
                                         " WHERE project_id = %(project_id)s AND project_setting = 'project_postprocessing' ORDER BY table_id"),
                                        {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['project_postprocessing'] = ','.join(str(v['project_postprocessing']) for v in project_postprocessing)
        data[0]['folders'] = folders
        project_stats = run_query(("SELECT "
                                        "collex_total, collex_to_digitize, collex_ready, objects_digitized, "
                                        "images_taken, images_in_dams, images_in_cis, images_public, "
                                        "no_records_in_cis, no_records_in_collexweb, no_records_in_collectionssiedu, "
                                        "no_records_in_gbif, cast(updated_at AS DATE) as updated_at "
                                        "FROM projects_stats WHERE project_id = %(project_id)s"),
                                       {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['project_stats'] = project_stats[0]
        # Reports
        reports = run_query(
            "SELECT report_id, report_title, updated_at FROM data_reports WHERE project_id = %(project_id)s",
            {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['reports'] = reports
    cur.close()
    conn.close()
    return jsonify(data[0])


@osprey_api.route('/api/update/<project_alias>', methods=['POST'], strict_slashes=False, provide_automatic_options=False)
def api_update_project_details(project_alias=None):
    """Update a project properties."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logger.error(e)
        return jsonify({'error': 'API error'}), 500
    api_key = request.form.get("api_key")
    logger.info("api_key: {}".format(api_key))
    if api_key is None:
        return jsonify({'error': 'Missing key'}), 401
    else:
        if validate_api_key(api_key, cur=cur):
            # Get project_id
            project_id = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s", {'project_alias': project_alias}, cur=cur)
            if len(project_id) == 0:
                return jsonify({'error': 'Invalid project'}), 401
            else:
                project_id = project_id[0]['project_id']
            # Value to update
            query_type = request.form.get("type")
            query_property = request.form.get("property")
            query_value = request.form.get("value")
            if query_type is not None and query_property is not None and query_value is not None:
                if query_type == "startup":
                    query = ("DELETE FROM folders_badges WHERE badge_type = 'verification' and folder_id in (SELECT folder_id from folders WHERE project_id = %(project_id)s)")
                    res = run_query(query, {'project_id': project_id}, cur=cur, return_val=False)
                    cur.close()
                    conn.close()
                    return jsonify({"result": True})
                elif query_type == "folder":
                    folder_id = request.form.get("folder_id")
                    if folder_id is not None:
                        if query_property == "status0":
                            query = ("UPDATE folders SET status = 0, error_info = NULL WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id}, cur=cur)
                        elif query_property == "status9":
                            query = (
                                "UPDATE folders SET status = 9, error_info = %(value)s WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                        elif query_property == "status1":
                            query = (
                                "UPDATE folders SET status = 1, error_info = %(value)s WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
                                " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'msg': query_value}, cur=cur)
                        elif query_property == "checking_folder":
                            # Clear badges
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'no_files'",
                                {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'error_files'",
                                {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_raw_md5'",
                                {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_md5'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'verification', 'bg-secondary', 'Folder under verification...', CURRENT_TIMESTAMP)")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                        elif query_property == "stats":
                            # Clear badges
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'no_files'", {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'error_files'",{'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'verification'", {'folder_id': folder_id}, cur=cur)
                            # Badge of no_files
                            no_files = run_query("SELECT COUNT(*) AS no_files FROM files WHERE folder_id = %(folder_id)s", {'folder_id': folder_id}, cur=cur)
                            if no_files[0]['no_files'] > 0:
                                if no_files[0]['no_files'] == 1:
                                    no_folder_files = "1 file"
                                else:
                                    no_folder_files = "{} files".format(no_files[0]['no_files'])
                                query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                         " VALUES (%(folder_id)s, 'no_files', 'bg-primary', %(no_files)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                                         " badge_css = 'bg-primary', updated_at = CURRENT_TIMESTAMP")
                                res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files}, cur=cur)
                            # Badge of error files
                            query = ("UPDATE folders f SET f.file_errors = 0 where folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            query = ("WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_id) > 0 THEN 1 ELSE 0 END AS no_files, %(folder_id)s as folder_id FROM files_checks c, files f"
                                        " WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 1)"
                                        " UPDATE folders f, data d SET f.file_errors = d.no_files "
                                        "WHERE f.folder_id = d.folder_id")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            no_files = run_query("SELECT file_errors FROM folders WHERE folder_id = %(folder_id)s", {'folder_id': folder_id}, cur=cur)
                            if no_files[0]['file_errors'] == 1:
                                query = (
                                    "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                    " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                                    "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                                res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files}, cur=cur)
                            # Update project
                            ## Update count
                            query = ("with data as "
                                     "  (select fol.project_id, count(f.file_name) as no_files "
                                     "          from files f, folders fol "
                                     "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                     "UPDATE projects_stats p, data SET p.images_taken = data.no_files where p.project_id = data.project_id")
                            res = query_database_insert(query, {'project_id': project_id}, cur=cur)
                            ## Get query for no. of objects
                            query_obj = run_query("SELECT project_object_query FROM projects WHERE project_id = %(project_id)s",
                                                 {'project_id': project_id}, cur=cur)[0]
                            query = ("with data as "
                                     "  (select fol.project_id, {} as no_objects"
                                     "          from files f, folders fol "
                                     "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                     "UPDATE projects_stats p, data SET p.objects_digitized = data.no_objects where p.project_id = data.project_id".format(query_obj['project_object_query'].replace('\\', '')))
                            res = query_database_insert(query, {'project_id': project_id}, cur=cur)
                            ## Get query for no. of other stat
                            query_stat_other = run_query("SELECT other_stat_calc FROM projects_stats WHERE project_id = %(project_id)s",
                                                 {'project_id': project_id}, cur=cur)
                            if query_stat_other[0]['other_stat_calc'] != None:
                                query = ("with data as "
                                        "  (select fol.project_id, {} as no_objects"
                                        "          from files f, folders fol "
                                        "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                        "UPDATE projects_stats p, data SET p.other_stat = data.no_objects where p.project_id = data.project_id".format(query_stat_other[0]['other_stat_calc'].replace('\\', '')))
                                res = query_database_insert(query, {'project_id': project_id}, cur=cur)
                        elif query_property == "raw0":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                     " VALUES (%(folder_id)s, %(value)s, 0) ON DUPLICATE KEY UPDATE md5 = 0")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                        elif query_property == "raw1":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                     " VALUES (%(folder_id)s, %(value)s, 1) ON DUPLICATE KEY UPDATE md5 = 1")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                        elif query_property == "tif_md5_exists":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                               " VALUES (%(folder_id)s, 'tif', %(value)s) ON DUPLICATE KEY UPDATE md5 = %(value)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                            if query_value == 1:
                                query = (
                                    "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                    " VALUES (%(folder_id)s, 'md5_files', 'bg-danger', 'MD5 files missing', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = 'MD5 files missing',"
                                    "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                                res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                        elif query_property == "tif_md5_matches_error":
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_md5', 'bg-danger', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': "Main {}".format(query_value)}, cur=cur)
                        elif query_property == "tif_md5_matches_ok":
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_md5'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_md5', 'bg-success', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-success', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': 'Main MD5 Valid'}, cur=cur)
                        elif query_property == "raw_md5_matches_error":
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_raw_md5', 'bg-danger', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': "RAW {}".format(query_value)}, cur=cur)
                        elif query_property == "raw_md5_matches_ok":
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_raw_md5'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_raw_md5', 'bg-success', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-success', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': 'RAW MD5 Valid'}, cur=cur)
                        elif query_property == "raw_md5_exists":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                               " VALUES (%(folder_id)s, 'raw', %(value)s) ON DUPLICATE KEY UPDATE md5 = %(value)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'md5_files', 'bg-danger', 'MD5 files missing', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = 'MD5 files missing',"
                                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            if query_value == 1:
                                res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                        elif query_property == "qc":
                            query = ("SELECT * FROM qc_folders WHERE folder_id = %(folder_id)s")
                            folder_qc = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            if len(folder_qc[0]) == 0:
                                qc_status = "QC Pending"
                                badge_css = "bg-secondary"
                            else:
                                folder_qc_status = folder_qc[0]['qc_status']
                                if folder_qc_status == 0:
                                    qc_status = "QC Passed"
                                    badge_css = "bg-success"
                                elif folder_qc_status ==1:
                                    qc_status = "QC Failed"
                                    badge_css = "bg-danger"
                                elif folder_qc_status == 9:
                                    qc_status = "QC Pending"
                                    badge_css = "bg-secondary"
                            query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'qc_status', %(badge_css)s, %(qc_status)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(qc_status)s,"
                                "       badge_css = %(badge_css)s, updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'qc_status': qc_status, 'badge_css': badge_css, 'folder_id': folder_id}, cur=cur)
                        else:
                            raise InvalidUsage('Invalid operation', status_code=401)
                        cur.close()
                        conn.close()
                        return jsonify({"result": True})
                elif query_type == "file":
                    file_id = request.form.get("file_id")
                    folder_id = request.form.get("folder_id")
                    if query_property == "unique":
                        # Check if file is unique
                        query = ("SELECT f.file_id, fol.project_folder FROM files f, folders fol "
                                 " WHERE f.folder_id = fol.folder_id AND f.file_id = %(file_id)s AND f.folder_id != %(folder_id)s"
                                 " AND f.folder_id IN (SELECT folder_id from folders where project_id = %(project_id)s)")
                        res = run_query(query,
                                        {'file_id': file_id, 'folder_id': folder_id, 'project_id': project_id},
                                        cur=cur)
                        if len(res) == 0:
                            check_results = 0
                            check_info = ""
                        elif len(res) == 1:
                            check_results = 1
                            conflict_folder = res[0]['project_folder']
                            check_info = "File with the same name in folder: {}".format(conflict_folder)
                        else:
                            check_results = 1
                            conflict_folder = []
                            for row in res:
                                conflict_folder.append(row['project_folder'])
                            conflict_folder = ', '.join(conflict_folder)
                            check_info = "Files with the same name in folders: {}".format(conflict_folder)
                        query = (
                            "INSERT INTO files_checks (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'folder_id': folder_id,
                                                     'check_results': check_results, 'check_info': check_info}, cur=cur)
                    elif query_property == "filechecks":
                        # Add to server side:
                        #  - dupe_elsewhere
                        #  - md5
                        folder_id = request.form.get("folder_id")
                        file_check = request.form.get("file_check")
                        check_results = query_value
                        check_info = request.form.get("check_info")
                        if file_check == 'filename':
                            query = ("SELECT settings_details FROM projects_settings "
                                 " WHERE project_id = %(project_id)s AND project_setting = 'project_checks' and settings_value = 'filename'")
                            res = run_query(query, {'project_id': project_id}, cur=cur)
                            if len(res) == 0:
                                check_results = 1
                                check_info = "Query for filename not found"
                            else:
                                query = res[0]['settings_details']
                                res = run_query(query, {'file_id': file_id,}, cur=cur)
                                logger.info(res)
                                # Get results for file query
                                check_results = res[0]['result']
                                check_info = res[0]['info']
                        query = (
                            "INSERT INTO files_checks (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                            " VALUES (%(file_id)s, %(folder_id)s, %(file_check)s, %(check_results)s, %(check_info)s, CURRENT_TIME) "
                            " ON DUPLICATE KEY UPDATE "
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        logger.info(query)
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'folder_id': folder_id,
                                                     'file_check': file_check,
                                                     'check_results': check_results, 'check_info': check_info}, cur=cur)
                        logger.info(res)
                    elif query_property == "filemd5":
                        filetype = request.form.get("filetype")
                        folder_id = request.form.get("folder_id")
                        query = ("INSERT INTO file_md5 (file_id, filetype, md5) "
                                 " VALUES (%(file_id)s, %(filetype)s, %(value)s) ON DUPLICATE KEY UPDATE md5 = %(value)s")
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'filetype': filetype, 'value': query_value}, cur=cur)
                    elif query_property == "exif":
                        filetype = request.form.get("filetype")
                        data_json = json.loads(query_value)
                        # exif_data = []
                        query = ("INSERT INTO files_exif (file_id, filetype, taggroup, tag, tagid, value) "
                                 " VALUES (%s, %s, %s, %s, %s, %s) "
                                 " ON DUPLICATE KEY UPDATE value = %s")
                        for key in data_json[0].keys():
                            if key == 'SourceFile':
                                continue
                            else:
                                for k, item in data_json[0][key].items():
                                    if k == "id":
                                        this_key = item
                                    else:
                                        if type(item) == 'list':
                                            this_val = ', '.join(item)
                                        else:
                                            this_val = str(item)
                                row_data = (file_id, filetype, key.split(':')[0], key.split(':')[1], this_key, this_val, this_val)
                                res = query_database_insert(query, row_data, cur=cur)
                            # Remove directory entries that reveal system paths
                            res = run_query("delete from files_exif where taggroup = 'System' and tag = 'Directory' and file_id = %(file_id)s;", 
                                            {'file_id': file_id}, return_val=False, cur=cur)
                    elif query_property == "delete":
                        query = ("DELETE FROM files WHERE file_id = %(file_id)s")
                        res = query_database_insert(query, {'file_id': file_id}, cur=cur)
                    else:
                        raise InvalidUsage('Invalid value for property', status_code=400)
                    cur.close()
                    conn.close()
                    return jsonify({"result": True})
                else:
                    return jsonify({'error': 'Invalid value for type: {}'.format(query_type)}), 400
            else:
                return jsonify({'error': 'Missing args'}), 400
        else:
            return jsonify({'error': 'Unauthorized'}), 401


@osprey_api.route('/api/new/<project_alias>', methods=['POST'], strict_slashes=False, provide_automatic_options=False)
def api_new_folder(project_alias=None):
    """Update a project properties."""
    api_key = request.form.get("api_key")
    logger.info("api_key: {}".format(api_key))
    if api_key is None:
        return jsonify({'error': 'Missing key'}), 401
    else:
        # Connect to db
        try:
            conn = pymysql.connect(host=settings.host,
                                   user=settings.user,
                                   passwd=settings.password,
                                   database=settings.database,
                                   port=settings.port,
                                   charset='utf8mb4',
                                   cursorclass=pymysql.cursors.DictCursor,
                                   autocommit=True)
            cur = conn.cursor()
        except pymysql.Error as e:
            logger.error(e)
            return jsonify({'error': 'API error'}), 500

        if validate_api_key(api_key, cur=cur):
            # Get project_id
            results = run_query("SELECT project_id from projects WHERE project_alias = %(project_alias)s",
                                     {'project_alias': project_alias}, cur=cur)
            project_id = results[0]['project_id']
            # New folder info
            query_type = request.form.get("type")
            if query_type is not None:
                if query_type == "folder":
                    folder = request.form.get("folder")
                    folder_path = request.form.get("folder_path")
                    project_id = request.form.get("project_id")
                    folder_date = request.form.get("folder_date")
                    if folder is not None and folder_path is not None:
                        query = ("INSERT INTO folders (project_folder, folder_path, status, project_id, date) "
                                 " VALUES (%(folder)s, %(folder_path)s, 0, %(project_id)s, %(folder_date)s)")
                        data = query_database_insert(query, {'folder': folder, 'folder_path': folder_path,
                                                             'project_id': project_id, 'folder_date': folder_date},
                                                     return_res=True, cur=cur)
                        data = run_query("SELECT * FROM folders WHERE project_folder = %(project_folder)s AND folder_path = %(folder_path)s AND project_id = %(project_id)s",
                                              {'project_folder': folder, 'folder_path': folder_path, 'project_id': project_id}, cur=cur)
                        cur.close()
                        conn.close()
                        return jsonify({"result": data})
                    else:
                        return jsonify({'error': 'Missing args'}), 400
                elif query_type == "file":
                    filename = request.form.get("filename")
                    timestamp = request.form.get("timestamp")
                    folder_id = request.form.get("folder_id")
                    filetype = request.form.get("filetype")
                    if filename is not None and timestamp is not None and folder_id is not None:
                        query = ("INSERT INTO files (folder_id, file_name, file_timestamp, uid, file_ext) "
                                 "  VALUES (%(folder_id)s, %(filename)s, %(timestamp)s, uuid_v4s(), %(file_ext)s)")
                        data = query_database_insert(query, {'folder_id': folder_id, 'filename': filename,
                                                             'timestamp': timestamp, 'file_ext': filetype}, cur=cur)
                        logger.debug("new_file:{}".format(data))
                        query = ("SELECT file_id, uid FROM files WHERE folder_id = %(folder_id)s AND file_name = %(filename)s")
                        file_info = run_query(query, {'folder_id': folder_id, 'filename': filename}, cur=cur)
                        file_id = file_info[0]['file_id']
                        file_uid = file_info[0]['uid']
                        # Check for unique file
                        query = ("SELECT f.file_id, fol.project_folder FROM files f, folders fol "
                                 " WHERE f.folder_id = fol.folder_id AND f.file_name = %(filename)s AND f.folder_id != %(folder_id)s"
                                 " AND f.folder_id IN (SELECT folder_id from folders where project_id = %(project_id)s)")
                        res = run_query(query,
                                             {'filename': filename, 'folder_id': folder_id, 'project_id': project_id}, cur=cur)
                        if len(res) == 0:
                            check_results = 0
                            check_info = ""
                        elif len(res) == 1:
                            check_results = 1
                            conflict_folder = res[0]['project_folder']
                            check_info = "File with the same name in folder: {}".format(conflict_folder)
                        else:
                            check_results = 1
                            conflict_folder = []
                            for row in res:
                                conflict_folder.append(row['project_folder'])
                            conflict_folder = ', '.join(conflict_folder)
                            check_info = "Files with the same name in folders: {}".format(conflict_folder)
                        query = ("INSERT INTO files_checks (file_id, uid, folder_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(uid)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'folder_id': folder_id,
                                                     'check_results': check_results, 'check_info': check_info, 'uid': file_uid}, cur=cur)
                        query = ("SELECT * FROM files WHERE file_id = %(file_id)s")
                        data = run_query(query, {'file_id': file_id}, cur=cur)
                        cur.close()
                        conn.close()
                        return jsonify({"result": data})
                    else:
                        return jsonify({'error': 'Missing args'}), 400
                elif query_type == "filesize":
                    file_id = request.form.get("file_id")
                    filetype = request.form.get("filetype")
                    filesize = request.form.get("filesize")
                    if file_id is not None and filetype is not None and filesize is not None:
                        query = ("INSERT INTO files_size (file_id, filetype, filesize) "
                                 " VALUES (%(file_id)s, %(filetype)s, %(filesize)s) ON DUPLICATE KEY UPDATE "
                                 " filesize = %(filesize)s")
                        data = query_database_insert(query,
                                                     {'file_id': file_id, 'filetype': filetype, 'filesize': filesize}, cur=cur)
                        cur.close()
                        conn.close()
                        return jsonify({"result": data})
                    else:
                        return jsonify({'error': 'Missing args'}), 400
                else:
                    return jsonify({'error': 'Invalid value for type'}), 400
            else:
                return jsonify({'error': 'Missing args'}), 400
        else:
            return jsonify({'error': 'Unauthorized'}), 401


@osprey_api.route('/api/folders/<int:folder_id>', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_details(folder_id=None):
    """Get the details of a folder and the list of files."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logger.error(e)
        return jsonify({'error': 'API error'}), 500

    data = run_query(("SELECT f.folder_id, f.project_id, f.project_folder as folder, f.status, "
                           "   f.notes, f.date, coalesce(f.no_files, 0) as no_files, f.file_errors, f.error_info, "
                            " CASE WHEN f.delivered_to_dams = 0 THEN 'Completed' "
                              "              WHEN f.delivered_to_dams = 1 THEN 'Ready' "
                              "              WHEN f.delivered_to_dams = 9 THEN 'Pending' END as delivered_to_dams, "
                           " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                              "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                              "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                              "          'QC Pending') as qc_status "
                        " FROM folders f "
                     " LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id) "
                      " WHERE f.folder_id = %(folder_id)s"), {'folder_id': folder_id}, cur=cur)
    project_id = data[0]['project_id']
    if len(data) == 1:
        api_key = request.form.get("api_key")
        logger.info("api_key: {}".format(api_key))
        if api_key is None:
            query = ("SELECT f.file_id, f.folder_id, f.file_name, DATE_FORMAT(f.file_timestamp, '%%Y-%%m-%%d %%H:%%i:%%S') as file_timestamp, "
                 " f.dams_uan, f.preview_image, DATE_FORMAT(f.updated_at, '%%Y-%%m-%%d %%H:%%i:%%S') as updated_at, "
                 " DATE_FORMAT(f.created_at, '%%Y-%%m-%%d %%H:%%i:%%S') AS created_at, m.md5 as tif_md5 "
                 " FROM files f LEFT JOIN file_md5 m ON (f.file_id = m.file_id AND lower(m.filetype)='tif') WHERE f.folder_id = %(folder_id)s")
            files = run_query(query, {'folder_id': folder_id}, cur=cur)
            data[0]['files'] = files
        else:
            if validate_api_key(api_key, cur=cur):
                filechecks_list_temp = run_query(
                    ("SELECT settings_value as file_check FROM projects_settings "
                     " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
                    {'project_id': project_id}, cur=cur)
                filechecks_list = []
                for fcheck in filechecks_list_temp:
                    filechecks_list.append(fcheck['file_check'])

                query = (
                    "SELECT f.file_id, f.folder_id, f.file_name, DATE_FORMAT(f.file_timestamp, '%%Y-%%m-%%d %%H:%%i:%%S') as file_timestamp, "
                    " f.dams_uan, f.preview_image, DATE_FORMAT(f.updated_at, '%%Y-%%m-%%d %%H:%%i:%%S') as updated_at, "
                    " DATE_FORMAT(f.created_at, '%%Y-%%m-%%d %%H:%%i:%%S') AS created_at, m.md5 as tif_md5 "
                    " FROM files f LEFT JOIN file_md5 m ON (f.file_id = m.file_id AND lower(m.filetype)='tif') WHERE f.folder_id = %(folder_id)s")
                files_list = run_query(query, {'folder_id': folder_id}, cur=cur)
                folder_files_df = pd.DataFrame(files_list)
                for fcheck in filechecks_list:
                    logger.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                         "   CASE WHEN check_results = 0 THEN 'OK' "
                                                         "       WHEN check_results = 9 THEN 'Pending' "
                                                         "       WHEN check_results = 1 THEN 'Failed' "
                                                         "       ELSE 'Pending' END as {fcheck} "
                                                         " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                         "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                        {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
                files = folder_files_df
                data[0]['files'] = files.to_dict('records')
        cur.close()
        conn.close()
        return jsonify(data[0])
    else:
        return None


@osprey_api.route('/api/folders/qc/<int:folder_id>', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_qc(folder_id=None):
    """Get the details of a folder and the list of files."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logger.error(e)
        return jsonify({'error': 'API error'}), 500

    api_key = request.form.get("api_key")
    logger.info("api_key: {}".format(api_key))

    if validate_api_key(api_key, cur=cur):
        query = (
            "SELECT f.file_name, DATE_FORMAT(f.file_timestamp, '%%Y-%%m-%%d %%H:%%i:%%S') as file_timestamp, "
            " CASE WHEN q.file_qc = 0 THEN 'Image OK' WHEN q.file_qc = 1 THEN 'Critical Issue' "
            "   WHEN q.file_qc = 2 THEN 'Major Issue' WHEN q.file_qc = 3 THEN 'Minor Issue' END AS file_qc, "
            " q.qc_info, u.full_name, DATE_FORMAT(q.updated_at, '%%Y-%%m-%%d %%H:%%i:%%S') as updated_at "
            " FROM qc_files q, files f, users u WHERE q.folder_id = %(folder_id)s AND q.file_id = f.file_id "
            "       AND q.qc_by = u.user_id ")
        data1 = run_query(query, {'folder_id': folder_id}, cur=cur)
        data = {}
        data['qc'] = data1
        cur.close()
        conn.close()
        return jsonify(data)
    else:
        cur.close()
        conn.close()
        return None


@osprey_api.route('/api/files/<file_id>', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_get_file_details(file_id=None):
    """Get the details of a file."""

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logger.error(e)
        return jsonify({'error': 'API error'}), 500

    file_id, file_uid = check_file_id(file_id, cur=cur)

    if file_id is None:
        return None

    data = run_query(("SELECT uid as osprey_id, folder_id, file_name, cast(file_timestamp AS DATETIME) as file_timestamp, "
                           "   dams_uan, preview_image, cast(updated_at AS DATETIME) as updated_at, "
                           "   cast(created_at AS DATETIME) as created_at "
                           " FROM files WHERE file_id = %(file_id)s"),
                          {'file_id': file_id}, cur=cur)
    if len(data) == 1:
        filechecks = run_query(
            ("WITH data AS (SELECT settings_value as file_check, %(file_id)s as file_id FROM projects_settings " 
                " WHERE project_setting = 'project_checks' and project_id IN (SELECT project_id FROM folders WHERE folder_id in (SElect folder_id from files where file_id = %(file_id)s ))) "
                 " SELECT f.check_info, CASE WHEN f.check_results IS NULL THEN 9 ELSE f.check_results END as check_results, d.file_check, cast(f.updated_at AS DATETIME) as updated_at " 
                 " FROM data d LEFT JOIN files_checks f ON (d.file_id = f.file_id and d.file_check = f.file_check)"),
            {'file_id': file_id}, cur=cur)
        data[0]['file_checks'] = filechecks
        file_exif = run_query(
            ("SELECT tag, value, filetype, tagid, taggroup, cast(updated_at AS DATETIME) as updated_at "
             " FROM files_exif WHERE file_id = %(file_id)s "
             " UNION "
             " SELECT tag, value, filetype, tagid, taggroup, cast(updated_at AS DATETIME) as updated_at "
             " FROM files_exif_old WHERE file_id = %(file_id)s"),
            {'file_id': file_id}, cur=cur)
        data[0]['exif'] = file_exif
        file_md5 = run_query(("SELECT filetype, md5, cast(updated_at AS DATETIME) as updated_at "
                                   "FROM file_md5 WHERE file_id = %(file_id)s"),
                                  {'file_id': file_id}, cur=cur)
        data[0]['md5_hashes'] = file_md5
        file_links = run_query(
            ("SELECT link_name, link_url, link_notes, cast(updated_at AS DATETIME) as updated_at "
             "FROM files_links WHERE file_id = %(file_id)s"),
            {'file_id': file_id}, cur=cur)
        data[0]['links'] = file_links
        file_post = run_query(
            ("SELECT post_step, post_results, post_info, cast(updated_at AS DATETIME) as updated_at "
             "FROM file_postprocessing WHERE file_id = %(file_id)s"),
            {'file_id': file_id}, cur=cur)
        data[0]['file_postprocessing'] = file_post
        val = jsonify(data[0])
    else:
        val = jsonify(None)
    cur.close()
    conn.close()
    return val


@osprey_api.route('/api/reports/<report_id>/', methods=['GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_report(report_id=None):
    """Get the data from a project report."""
    if report_id is None:
        return None
    else:
        # Connect to db
        try:
            conn = pymysql.connect(host=settings.host,
                                   user=settings.user,
                                   passwd=settings.password,
                                   database=settings.database,
                                   port=settings.port,
                                   charset='utf8mb4',
                                   cursorclass=pymysql.cursors.DictCursor,
                                   autocommit=True)
            cur = conn.cursor()
        except pymysql.Error as e:
            logger.error(e)
            return jsonify({'error': 'API error'}), 500

        file_name = request.args.get("file_name")
        dams_uan = request.args.get("dams_uan")
        logger.info("file_name: {}".format(file_name))
        logger.info("dams_uan: {}".format(dams_uan))
        query = run_query("SELECT * FROM data_reports WHERE report_id = %(report_id)s",
                               {'report_id': report_id}, cur=cur)
        if len(query) == 0:
            query = run_query("SELECT * FROM data_reports WHERE report_alias = %(report_id)s",
                                   {'report_id': report_id}, cur=cur)
            if len(query) == 0:
                return None
        if file_name is not None and dams_uan is not None:
            return None
        elif file_name is not None and dams_uan is None:
            data = run_query(
                "SELECT * FROM ({}) a WHERE file_name = %(file_name)s".format(query[0]['query_api'].replace('%', '%%')),
                {'file_name': file_name}, cur=cur)
        elif dams_uan is not None and file_name is None:
            data = run_query(
                "SELECT * FROM ({}) a WHERE dams_uan = %(dams_uan)s".format(query[0]['query_api'].replace('%', '%%')),
                {'dams_uan': dams_uan}, cur=cur)
        else:
            data = run_query(query[0]['query_api'], cur=cur)
        cur.close()
        conn.close()
        return jsonify(data)

