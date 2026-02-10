#!flask/bin/python
#
# Osprey API
#
# Import flask
from flask import Flask
from flask import jsonify
from flask import request
import uuid
import json
import pandas as pd
import locale

import requests

# MySQL
import mysql.connector

from cache import cache
# Logging
from logger import logger

import settings

site_ver = "2.11.0"
site_env = "api"
site_net = "api"

logger.info("site_ver = {}".format(site_ver))
logger.info("site_env = api".format(site_env))
logger.info("site_net = api".format(site_net))

# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

app = Flask(__name__)
app.secret_key = settings.secret_key

# Add logger
app.logger.addHandler(logger)

# Setup cache
cache.init_app(app)

# Disable strict trailing slashes
app.url_map.strict_slashes = False


# Connect to Mysql 
try:
    conn = mysql.connector.connect(host=settings.host,
                            user=settings.user,
                            password=settings.password,
                            database=settings.database,
                            port=settings.port, 
                            autocommit=True, 
                            connection_timeout=60)
    conn.time_zone = '-04:00'
    cur = conn.cursor(dictionary=True)
except mysql.connector.Error as err:
    logger.error(err)
    

################################
# Functions
################################
def run_query(query, parameters=None, return_val=True):
    logger.info("parameters: {}".format(parameters))
    logger.info("query: {}".format(query))
    # Check connection to DB and reconnect if needed
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)
    except mysql.connector.InterfaceError as error:
        logger.error("mysql connection error: {}".format(error))
        return False
    # Run query
    if parameters is None:
        try:
            results = cur.execute(query)
        except mysql.connector.Error  as err:
            logger.error("mysql error: {} (err_no: {}|query: {})".format(err, err.errno, query))
            return False
    else:
        try:
            results = cur.execute(query, parameters)
        except mysql.connector.Error  as err:
            logger.error("mysql error: {} (err_no: {}|query: {})".format(err, err.errno, query))
            return False
    if return_val:
        data = cur.fetchall()
        logger.info("No of results: ".format(len(data)))
        return data
    else:
        return True


def query_database_insert(query, parameters, return_res=False):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    # Check connection to DB and reconnect if needed
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)
    except mysql.connector.InterfaceError as error:
        logger.error("mysql connection error: {}".format(error))
        return False
    # Run query
    data = True
    try:
        results = cur.execute(query, parameters)
    except Exception as error:
        logger.error(error)
        return jsonify({'error': 'API Error'}), 500
    if return_res:
        data = cur.fetchall()
        logger.info("No of results: ".format(len(data)))
        if len(data) == 0:
            data = False
    return data


def validate_api_key(api_key=None, url=None, params=None):
    logger.info("api_key: {}".format(api_key))
    if api_key is None:
        return False, False
    try:
        api_key_check = uuid.UUID(api_key)
    except ValueError:
        return False, False
    # Run query
    query = ("SELECT api_key, is_admin from api_keys WHERE api_key = %(api_key)s and is_active = 1")
    parameters = {'api_key': api_key}
    data = run_query(query, parameters=parameters, return_val=True)
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    if len(data) == 1:
        if data[0]['api_key'] == api_key:
            if data[0]['is_admin'] != 1:
                query = ("INSERT INTO api_keys_usage (api_key, valid, url, params) VALUES (%(api_key)s, 1, %(url)s, %(params)s)")
                params = {'api_key': api_key, 'url': url, 'params': params}
                query_database_insert(query, params)
            return True, data[0]['is_admin'] == 1
        else:
            query = ("INSERT INTO api_keys_usage (api_key, valid) VALUES (%(api_key)s, 0, %(url)s, %(params)s)")
            params = {'api_key': api_key, 'url': url, 'params': params}
            query_database_insert(query, params)
            return False, False
    else:
        query = ("INSERT INTO api_keys_usage (api_key, valid) VALUES (%(api_key)s, 0, %(url)s, %(params)s)")
        params = {'api_key': api_key, 'url': url, 'params': params}
        query_database_insert(query, params)
        return False, False


def check_file_id(file_id=None):
    if file_id is None:
        return False, False
    try:
        file_id = int(file_id)
        file_id_type = "int"
    except ValueError:
        try:
            file_uid = uuid.UUID(file_id, version=4)
            file_id_type = "uuid"
        except ValueError:
            return False, False
    if file_id_type == "uuid":
        file_id = run_query("SELECT file_id FROM files WHERE uid = %(uid)s", {'uid': file_uid})
        if len(file_id) == 0:
            return False, False
        else:
            return file_id[0]['file_id'], file_uid
    else:
        file_uid = run_query("SELECT uid FROM files WHERE file_id = %(file_id)s", {'file_id': file_id})
        if len(file_uid) == 0:
            return False, False
        else:
            return file_id, file_uid[0]['uid']


###################################
# Osprey API
###################################
@cache.memoize()
@app.route('/', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
def api_route_list():
    """Print available routes in JSON"""
    # Adapted from https://stackoverflow.com/a/17250154
    func_list = {}
    for rule in app.url_map.iter_rules():
        # Skip 'static' routes
        if str(rule).startswith('/new'):
            continue
        elif str(rule).startswith('/update'):
            continue
        elif str(rule) == '/reports/':
            continue
        else:
            func_list[rule.rule] = app.view_functions[rule.endpoint].__doc__
    data = {'routes': func_list, 'sys_ver': site_ver, 'env': site_env, 'net': site_net}
    return jsonify(data)


@app.route('/projects/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_projects():
    """Get the list of projects."""
    # Check api_key
    # api_key = request.form.get("api_key")
    # if api_key is None or api_key == "":
    #     return jsonify({'error': 'api_key is missing'}), 400
    # valid_api_key, is_admin = validate_api_key(api_key, url='/projects/', params=None)
    # if valid_api_key == False:
    #     return jsonify({'error': 'Forbidden'}), 403
    section = request.form.get("section")
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
                 " ORDER BY p.projects_order DESC")
        projects_data = run_query(query)
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
                 " ORDER BY p.projects_order DESC")
        projects_data = run_query(query, {'section': section})
    last_update = run_query("SELECT date_format(MAX(updated_at), '%d-%m-%Y') AS updated_at FROM projects_stats")
    data = ({"projects": projects_data, "last_update": last_update[0]['updated_at']})
    return jsonify(data)


@app.route('/projects/<project_alias>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_project_details(project_alias=None):
    """Get the details of a project by specifying the project_alias."""
    # Check api_key
    # api_key = request.form.get("api_key")
    # if api_key is None or api_key == "":
    #     return jsonify({'error': 'api_key is missing'}), 400
    # valid_api_key, is_admin = validate_api_key(api_key, url='/projects/', params="project_alias={}".format(project_alias))
    # if valid_api_key == False:
    #     return jsonify({'error': 'Forbidden'}), 403
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
                               "date_format(project_start, '%Y-%m-%d') AS project_start, "
                               "CASE WHEN project_end IS NULL THEN NULL ELSE date_format(project_end, '%Y-%m-%d') END as project_end, "
                               "project_notice, "
                               "date_format(updated_at, '%Y-%m-%d') AS updated_at, "
                               "transcription "
                               "FROM projects "
                               " WHERE project_alias = %(project_alias)s"),
                              {'project_alias': project_alias})
    if len(data) == 1:
        if data[0]['transcription'] == 1:
            folders = run_query(("SELECT "
                                        "f.folder_transcription_id as folder_id, f.project_id, f.folder, "
                                        "f.folder_path, f.status, "
                                        "f.error_info, date_format(f.date, '%Y-%m-%d') as capture_date, "
                                        "f.no_files, f.file_errors, "
                                        " CASE WHEN f.delivered_to_dams = 1 THEN 0 ELSE 9 END as delivered_to_dams, "
                                        " COALESCE(CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                                " WHEN q.qc_status = 1 THEN 'QC Failed' "
                                                " WHEN q.qc_status = 9 THEN 'QC Pending' END, 'QC Pending') as qc_status,"
                                        " GROUP_CONCAT(b.badge_text) as badges"
                                        " FROM transcription_folders f LEFT JOIN qc_folders q ON (f.folder_transcription_id = q.folder_uid)"
                                        "     LEFT JOIN folders_badges b ON (f.folder_transcription_id = b.folder_uid) "
                                        " WHERE project_id = %(project_id)s"
                                        " GROUP BY f.folder_transcription_id, f.project_id, f.folder, f.folder_path, "
                                        "      f.status, f.error_info, f.date, f.no_files,"
                                        "      f.file_errors, q.qc_status"),
                                        {'project_id': data[0]['project_id']})
        else:
            folders = run_query(("SELECT "
                                        "f.folder_id, f.project_id, f.project_folder as folder, "
                                        "f.folder_path, f.status, "
                                        "f.error_info, date_format(f.date, '%Y-%m-%d') as capture_date, "
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
                                        "      f.status, f.error_info, f.date, f.no_files,"
                                        "      f.file_errors, q.qc_status"),
                                        {'project_id': data[0]['project_id']})
        data[0]['folders'] = folders
        project_checks = run_query(("SELECT settings_value as project_check FROM projects_settings "
                                         " WHERE project_id = %(project_id)s AND project_setting = 'project_checks'"),
                                        {'project_id': data[0]['project_id']})
        data[0]['project_checks'] = ','.join(str(v['project_check']) for v in project_checks)
        project_postprocessing = run_query(("SELECT settings_value as project_postprocessing FROM projects_settings "
                                         " WHERE project_id = %(project_id)s AND project_setting = 'project_postprocessing' ORDER BY table_id"),
                                        {'project_id': data[0]['project_id']})
        data[0]['project_postprocessing'] = ','.join(str(v['project_postprocessing']) for v in project_postprocessing)
        project_stats = run_query(("SELECT "
                                        "collex_total, objects_digitized, "
                                        "images_taken "
                                        "FROM projects_stats WHERE project_id = %(project_id)s"),
                                       {'project_id': data[0]['project_id']})
        data[0]['project_stats'] = project_stats[0]
        # Reports
        reports = run_query(
            "SELECT report_id, report_title FROM data_reports WHERE project_id = %(project_id)s",
            {'project_id': data[0]['project_id']})
        data[0]['reports'] = reports
    else:
        return jsonify({'error': 'Project was not found'}), 404
    return jsonify(data[0])


@app.route('/projects/<project_alias>/files', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_project_files(project_alias=None):
    """Get the list of files of a project by specifying the project_alias."""
    # Check api_key
    # api_key = request.form.get("api_key")
    # if api_key is None or api_key == "":
    #     return jsonify({'result': False}), 400
    # valid_api_key, is_admin = validate_api_key(api_key, url='/projects/files', params="project_alias={}".format(project_alias))
    # if valid_api_key == False:
    #     return jsonify({'result': False}), 403
    data = run_query(("SELECT f.file_id, f.uid, f.file_name, f.folder_id FROM files f WHERE f.folder_id in "
                               " (SELECT folder_id FROM folders WHERE project_id in (SELECT project_id from projects WHERE project_alias = %(project_alias)s)) ORDER BY f.file_name"),
                              {'project_alias': project_alias})
    if len(data) == 0:
        return jsonify({'result': False}), 404
    else:
        return jsonify(data)


@app.route('/update/<project_alias>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_update_project_details(project_alias=None):
    """Update a project properties."""
    # Check api_key
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(api_key, url='/update/', params="project_alias={}".format(project_alias))
    if valid_api_key == False:
        return jsonify({'error': 'Forbidden'}), 403
    if is_admin == False:
        return jsonify({'error': 'Forbidden'}), 403
    else:
        # Get project_id
        project_id = run_query("SELECT project_id, transcription FROM projects WHERE project_alias = %(project_alias)s", {'project_alias': project_alias})
        if len(project_id) == 0:
            return jsonify({'error': 'Project not found'}), 404
        else:
            transcription = project_id[0]['transcription']
            project_id = project_id[0]['project_id']
        # Value to update
        query_type = request.form.get("type")
        query_property = request.form.get("property")
        query_value = request.form.get("value")
        if query_type is not None and query_property is not None and query_value is not None:
            if transcription == 1:
                folder_table = "transcription_folders"
                fid = "folder_uid"
                files_table = "transcription_files"
                fileid = "file_uid"
            else:
                folder_table = "folders"
                fid = "folder_id"
                files_table = "files"
                fileid = "file_id"
            if query_type == "startup":
                query = (f"DELETE FROM folders_badges WHERE badge_type = 'verification' and {fid} in (SELECT {fid} from {folder_table} WHERE project_id = %(project_id)s)")
                res = run_query(query, {'project_id': project_id}, return_val=False)
                query = (f"DELETE FROM folders_badges WHERE badge_type = 'filename_spaces' and {fid} in (SELECT {fid} from {folder_table} WHERE project_id = %(project_id)s)")
                res = run_query(query, {'project_id': project_id}, return_val=False)
                query = (f"DELETE FROM folders_badges WHERE badge_type = 'folder_error' and {fid} in (SELECT {fid} from {folder_table} WHERE project_id = %(project_id)s)")
                res = run_query(query, {'project_id': project_id}, return_val=False)
                query = (f"DELETE FROM folders_badges WHERE badge_type = 'error_files' and {fid} in (SELECT {fid} from {folder_table} WHERE project_id = %(project_id)s)")
                res = run_query(query, {'project_id': project_id}, return_val=False)
                return jsonify({"result": True})
            elif query_type == "folder":
                folder_id = request.form.get("folder_id")
                if folder_id is not None:
                    if query_property == "status0":
                        if transcription == 1:
                            query = (f"UPDATE transcription_folders SET status = 0, error_info = NULL WHERE folder_transcription_id = %(folder_id)s")
                            res = run_query(query, {'folder_id': folder_id})
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_uid = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id})
                        else:
                            query = (f"UPDATE folders SET status = 0, error_info = NULL WHERE folder_id = %(folder_id)s")
                            res = run_query(query, {'folder_id': folder_id})
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, clear_badges))
                    elif query_property == "status9":
                        query = (f"UPDATE {folder_table} SET status = 9, error_info = %(value)s WHERE {fid} = %(folder_id)s")
                        res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "status1":
                        if transcription == 1:
                            query = (f"UPDATE transcription_folders SET status = 1, error_info = %(value)s WHERE folder_transcription_id = %(folder_id)s")
                        else:
                            query = (f"UPDATE folders SET status = 1, error_info = %(value)s WHERE folder_id = %(folder_id)s")
                        res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_error'",
                            {'folder_id': folder_id})
                        query = (f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s, badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                        res = query_database_insert(query, {'folder_id': folder_id, 'msg': query_value})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "checking_folder":
                        # Clear badges
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'no_files'",
                            {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'error_files'",
                            {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_raw_md5'",
                            {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_md5'",
                            {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'verification'",
                            {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_error'",
                            {'folder_id': folder_id})
                        query = (f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) VALUES (%(folder_id)s, 'verification', 'bg-secondary', 'Folder under verification...', CURRENT_TIMESTAMP)")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        if transcription == 1:
                            query = ("UPDATE transcription_folders SET previews = 1 WHERE folder_transcription_id = %(folder_id)s")
                        else:
                            query = ("UPDATE folders SET previews = 1 WHERE folder_id = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "stats":
                        # Clear badges
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'no_files'", {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'error_files'",{'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'verification'", {'folder_id': folder_id})
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_error'", {'folder_id': folder_id})
                        # Badge of no_files
                        if transcription == 1:
                            no_files = run_query("SELECT COUNT(*) AS no_files FROM transcription_files WHERE folder_transcription_id = %(folder_id)s", {'folder_id': folder_id})
                        else:
                            no_files = run_query("SELECT COUNT(*) AS no_files FROM files WHERE folder_id = %(folder_id)s", {'folder_id': folder_id})
                        if no_files[0]['no_files'] > 0:
                            if no_files[0]['no_files'] == 1:
                                no_folder_files = "1 file"
                            else:
                                no_folder_files = "{} files".format(no_files[0]['no_files'])
                            query = (f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) VALUES (%(folder_id)s, 'no_files', 'bg-primary', %(no_files)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s, badge_css = 'bg-primary', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files})
                            logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        # Badge of error files
                        if transcription == 1:
                            query = ("UPDATE transcription_folders f SET f.file_errors = 0 where folder_transcription_id = %(folder_id)s")
                        else:
                            query = ("UPDATE folders f SET f.file_errors = 0 where folder_id = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        if transcription == 1:
                            query = ("WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_transcription_id) > 0 THEN 1 ELSE 0 END AS no_files, %(folder_id)s as folder_transcription_id "
                                    " FROM transcription_files_checks c, transcription_files f "
                                    " WHERE f.folder_transcription_id = %(folder_id)s AND f.file_transcription_id = c.file_transcription_id AND c.check_results = 1)"
                                    " UPDATE transcription_folders f, data d SET f.file_errors = d.no_files "
                                    "WHERE f.folder_transcription_id = d.folder_transcription_id")
                        else:
                            query = ("WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_id) > 0 THEN 1 ELSE 0 END AS no_files, %(folder_id)s as folder_id FROM files_checks c, files f"
                                    " WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 1)"
                                    " UPDATE folders f, data d SET f.file_errors = d.no_files "
                                    "WHERE f.folder_id = d.folder_id")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        if transcription == 1:
                            no_files = run_query(f"SELECT file_errors FROM transcription_folders WHERE folder_transcription_id = %(folder_id)s", {'folder_id': folder_id})
                        else:
                            no_files = run_query(f"SELECT file_errors FROM folders WHERE folder_id = %(folder_id)s", {'folder_id': folder_id})
                        if no_files[0]['file_errors'] == 1:
                            if transcription == 1:
                                query = ("INSERT INTO folders_badges (folder_uid, badge_type, badge_css, badge_text, updated_at) "
                                            " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                                            "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            else:
                                query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                            " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                                            "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files})
                            logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        # Update project
                        ## Update count
                        if transcription == 1:
                            query = ("with data as "
                                        "  (select fol.project_id, count(f.file_name) as no_files "
                                        "          from transcription_files f, transcription_folders fol "
                                        "          where fol.project_id = %(project_id)s and fol.folder_transcription_id =f.folder_transcription_id)"
                                        "UPDATE projects_stats p, data SET p.images_taken = data.no_files where p.project_id = data.project_id")
                        else:
                            query = ("with data as "
                                    "  (select fol.project_id, count(f.file_name) as no_files "
                                    "          from files f, folders fol "
                                    "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                    "UPDATE projects_stats p, data SET p.images_taken = data.no_files where p.project_id = data.project_id")
                        res = query_database_insert(query, {'project_id': project_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        ## Get query for no. of objects
                        query_obj = run_query("SELECT project_object_query FROM projects WHERE project_id = %(project_id)s",
                                                {'project_id': project_id})[0]
                        if transcription == 1:
                            query = ("with data as "
                                        "  (select fol.project_id, {} as no_objects"
                                        "          from transcription_files f, transcription_folders fol "
                                        "          where fol.project_id = %(project_id)s and fol.folder_transcription_id =f.folder_transcription_id)"
                                        "UPDATE projects_stats p, data SET p.objects_digitized = data.no_objects where p.project_id = data.project_id".format(query_obj['project_object_query'].replace('\\', '')))
                        else:
                            query = ("with data as "
                                        "  (select fol.project_id, {} as no_objects"
                                        "          from files f, folders fol "
                                        "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                        "UPDATE projects_stats p, data SET p.objects_digitized = data.no_objects where p.project_id = data.project_id".format(query_obj['project_object_query'].replace('\\', '')))
                        res = query_database_insert(query, {'project_id': project_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        ## Get query for no. of other stat
                        query_stat_other = run_query("SELECT other_stat_calc FROM projects_stats WHERE project_id = %(project_id)s",
                                                {'project_id': project_id})
                        if query_stat_other[0]['other_stat_calc'] != None:
                            if transcription == 1:
                                query = ("with data as "
                                        "  (select fol.project_id, {} as no_objects"
                                        "          from transcription_files f, transcription_folders fol "
                                        "          where fol.project_id = %(project_id)s and fol.folder_transcription_id =f.folder_transcription_id)"
                                        "UPDATE projects_stats p, data SET p.other_stat = data.no_objects where p.project_id = data.project_id".format(query_stat_other[0]['other_stat_calc'].replace('\\', '')))
                            else:
                                query = ("with data as "
                                    "  (select fol.project_id, {} as no_objects"
                                    "          from files f, folders fol "
                                    "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                    "UPDATE projects_stats p, data SET p.other_stat = data.no_objects where p.project_id = data.project_id".format(query_stat_other[0]['other_stat_calc'].replace('\\', '')))
                            res = query_database_insert(query, {'project_id': project_id})
                            logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        # Update updated_at datetime
                        if transcription == 1:
                            query = ("UPDATE transcription_folders SET updated_at = NOW() WHERE folder_transcription_id = %(folder_id)s")
                        else:
                            query = ("UPDATE folders SET updated_at = NOW() WHERE folder_id = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        # Check for other error badges
                        query_other_errors = run_query(f"SELECT count(*) as no_badges from folders_badges where {fid} = %(folder_id)s AND badge_css = 'bg-danger'",
                                                {'folder_id': folder_id})[0]
                        if query_other_errors['no_badges'] > 0:
                            if transcription == 1:
                                query = ("UPDATE transcription_folders f SET f.file_errors = 1 where folder_transcription_id = %(folder_id)s")
                            else:
                                query = ("UPDATE folders f SET f.file_errors = 1 where folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id})
                        # Calculate counts for folder
                        if transcription == 1:
                            no_files = run_query(f"SELECT count(*) as no_files FROM transcription_files WHERE folder_transcription_id = %(folder_id)s", {'folder_id': folder_id})[0]
                            res = query_database_insert(f"UPDATE transcription_folders SET no_files_total = %(no_files)s WHERE folder_transcription_id = %(folder_id)s", {'folder_id': folder_id, 'no_files': no_files['no_files']})
                            no_error_files = run_query("SELECT count(distinct f.file_transcription_id) as no_files FROM transcription_files f, transcription_files_checks fc WHERE f.folder_transcription_id = %(folder_id)s and f.file_transcription_id = fc.file_transcription_id AND fc.check_results = 1", {'folder_id': folder_id})[0]
                            res = query_database_insert(f"UPDATE transcription_folders SET no_files_errors = %(no_files)s WHERE folder_transcription_id = %(folder_id)s", {'folder_id': folder_id, 'no_files': no_error_files['no_files']})
                            no_ok_files = run_query("""
                                                with no_checks as (SELECT count(*) as no_checks FROM projects_settings WHERE project_id = %(project_id)s and project_setting = 'project_checks'),
                                                no_files as (
                                                SELECT f.file_transcription_id, count(*) as no_files FROM transcription_files f, transcription_files_checks fc 
                                                WHERE f.folder_transcription_id = %(folder_id)s and f.file_transcription_id = fc.file_transcription_id and fc.check_results = 0
                                                group by f.file_transcription_id)
                                                select count(no_files.file_transcription_id) as ok_files from no_files, no_checks where no_files.no_files = no_checks.no_checks
                                                    """,
                                                {'project_id': project_id, 'folder_id': folder_id})[0]
                            res = query_database_insert(f"UPDATE transcription_folders SET no_files_ok = %(no_files)s WHERE folder_transcription_id = %(folder_id)s", {'folder_id': folder_id, 'no_files': no_ok_files['ok_files']})
                            no_checks = run_query("SELECT count(*) as no_checks FROM projects_settings WHERE project_id = %(project_id)s and project_setting = 'project_checks'",
                                                {'project_id': project_id})[0]
                            total_checks = int(no_checks['no_checks']) * int(no_files['no_files'])
                            no_pending = run_query("SELECT count(*) as no_files from transcription_files_checks where file_transcription_id in (select file_transcription_id from transcription_files where folder_transcription_id = %(folder_id)s) and (check_results = 0 or check_results = 1)", {'folder_id': folder_id})[0]
                        else:
                            no_files = run_query(f"SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s", {'folder_id': folder_id})[0]
                            res = query_database_insert(f"UPDATE {folder_table} SET no_files_total = %(no_files)s WHERE {fid}= %(folder_id)s", {'folder_id': folder_id, 'no_files': no_files['no_files']})
                            no_error_files = run_query("SELECT count(distinct f.file_id) as no_files FROM files f, files_checks fc WHERE f.folder_id = %(folder_id)s and f.file_id = fc.file_id and fc.check_results = 1", {'folder_id': folder_id})[0]
                            res = query_database_insert(f"UPDATE folders SET no_files_errors = %(no_files)s WHERE folder_id = %(folder_id)s", {'folder_id': folder_id, 'no_files': no_error_files['no_files']})
                            no_ok_files = run_query("""
                                                with no_checks as (SELECT count(*) as no_checks FROM projects_settings WHERE project_id = %(project_id)s and project_setting = 'project_checks'),
                                                no_files as (
                                                SELECT f.file_id, count(*) as no_files FROM files f, files_checks fc 
                                                WHERE f.folder_id = %(folder_id)s and f.file_id = fc.file_id and fc.check_results = 0
                                                group by f.file_id)
                                                select count(no_files.file_id) as ok_files from no_files, no_checks where no_files.no_files = no_checks.no_checks
                                                    """,
                                                {'project_id': project_id, 'folder_id': folder_id})[0]
                            res = query_database_insert(f"UPDATE folders SET no_files_ok = %(no_files)s WHERE folder_id = %(folder_id)s", {'folder_id': folder_id, 'no_files': no_ok_files['ok_files']})
                            no_checks = run_query("SELECT count(*) as no_checks FROM projects_settings WHERE project_id = %(project_id)s and project_setting = 'project_checks'",
                                                {'project_id': project_id})[0]
                            total_checks = int(no_checks['no_checks']) * int(no_files['no_files'])
                            no_pending = run_query("SELECT count(*) as no_files from files_checks where file_id in (select file_id from files where folder_id = %(folder_id)s) and (check_results = 0 or check_results = 1)", {'folder_id': folder_id})[0]
                        # Verify all checks were completed
                        logger.info("641: {},{}".format(total_checks, no_pending['no_files']))
                        if total_checks != no_pending['no_files']:
                            if transcription == 1:
                                query = (f"UPDATE transcription_folders SET status = 1, error_info = %(value)s WHERE folder_transcription_id = %(folder_id)s")
                            else:
                                query = (f"UPDATE folders SET status = 1, error_info = %(value)s WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'value': "File checks totals don't match", 'folder_id': folder_id})
                            logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                            clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id})
                            if transcription == 1:
                                query = (
                                    "INSERT INTO folders_badges (folder_uid, badge_type, badge_css, badge_text, updated_at) "
                                    " VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
                                    " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            else:
                                query = (
                                    "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                    " VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
                                    " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'msg': "System Error"})
                            logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        # Update project counts
                        if transcription == 1:
                            query = ("""WITH folders_q AS (
                                            SELECT project_id,
                                                    SUM(no_files_total)  AS images_taken,
                                                    SUM(no_files_errors) AS project_err,
                                                    SUM(no_files_ok)     AS project_ok
                                            FROM transcription_folders
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
                                            WHERE s.project_id = 250
                                    """)
                        else:
                            query = ("""WITH folders_q AS (
                                            SELECT project_id,
                                                    SUM(no_files_total)  AS images_taken,
                                                    SUM(no_files_errors) AS project_err,
                                                    SUM(no_files_ok)     AS project_ok
                                            FROM folders
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
                                            WHERE s.project_id = 250
                                 """)
                        res = query_database_insert(query, {'project_id': project_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "raw0":
                        query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                    " VALUES (%(folder_id)s, %(value)s, 0) ON DUPLICATE KEY UPDATE md5 = 0")
                        res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "raw1":
                        query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                    " VALUES (%(folder_id)s, %(value)s, 1) ON DUPLICATE KEY UPDATE md5 = 1")
                        res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "tif_md5_matches_error":
                        query = (f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) VALUES (%(folder_id)s, 'folder_md5', 'bg-danger', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s, badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                        res = query_database_insert(query, {'folder_id': folder_id, 'value': query_value})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        query = (f"UPDATE {folder_table} SET status = 1 WHERE {fid} = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "tif_md5_matches_ok":
                        query = f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'folder_md5'"
                        clear_badges = run_query(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, clear_badges))
                        query = (f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) VALUES (%(folder_id)s, 'folder_md5', 'bg-success', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s, badge_css = 'bg-success', updated_at = CURRENT_TIMESTAMP")
                        res = query_database_insert(query, {'folder_id': folder_id, 'value': 'MD5 Valid'})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "filename_spaces":
                        query = (f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) VALUES (%(folder_id)s, 'filename_spaces', 'bg-danger', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s, badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                        res = query_database_insert(query, {'folder_id': folder_id, 'value': "Filenames Have Spaces"})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fid} = %(folder_id)s and badge_type = 'verification'", {'folder_id': folder_id})
                        if transcription == 1:
                            query = ("UPDATE transcription_folders SET status = 1 WHERE folder_transcription_id = %(folder_id)s")
                        else:
                            query = ("UPDATE folders SET status = 1 WHERE folder_id = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "previews":
                        query = (f"UPDATE {folder_table} SET previews = %(value)s WHERE {fid} = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id, 'value': query_value})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "qc":
                        query = ("SELECT * FROM qc_folders WHERE folder_id = %(folder_id)s")
                        folder_qc = query_database_insert(query, {'folder_id': folder_id})
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
                        res = query_database_insert(query, {'qc_status': qc_status, 'badge_css': badge_css, 'folder_id': folder_id})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    else:
                        return jsonify({'error': 'Invalid operation'}), 401
                    return jsonify({"result": True})
            elif query_type == "file":
                file_id = request.form.get("file_id")
                folder_id = request.form.get("folder_id")
                if query_property == "unique":
                    # Check if file is unique
                    if transcription == 1:
                        query = ("with fileinfo as (select * from transcription_files where file_transcription_id = %(file_id)s) "
                                " SELECT f.file_transcription_id as file_id, fol.folder as project_folder "
                                " FROM transcription_files f, transcription_folders fol, fileinfo finfo " 
                                " WHERE f.folder_transcription_id = fol.folder_transcription_id AND f.file_transcription_id != %(file_id)s AND f.folder_transcription_id != %(folder_id)s AND "
                                " f.folder_transcription_id IN (SELECT folder_transcription_id from transcription_folders where project_id = %(project_id)s) and "
                                "  f.file_name = finfo.file_name")
                    else:
                        query = ("with fileinfo as (select * from files where file_id = %(file_id)s) "
                                " SELECT f.file_id, fol.project_folder "
                                " FROM files f, folders fol, fileinfo finfo " 
                                " WHERE f.folder_id = fol.folder_id AND f.file_id != %(file_id)s AND f.folder_id != %(folder_id)s AND "
                                " f.folder_id IN (SELECT folder_id from folders where project_id = %(project_id)s) and "
                                "  f.file_name = finfo.file_name")
                    res = run_query(query, {'file_id': file_id, 'folder_id': folder_id, 'project_id': project_id})
                    if len(res) == 0:
                        check_results = 0
                        check_info = "File not found in the project"
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
                    if transcription == 1:
                        query = ("INSERT INTO transcription_files_checks "
                            " (file_transcription_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE "
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query, {'file_id': file_id, 'check_results': check_results, 'check_info': check_info})
                    else:
                        query = ("INSERT INTO files_checks "
                            " (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE "
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query, {'file_id': file_id, 'folder_id': folder_id, 'check_results': check_results, 'check_info': check_info})
                elif query_property == "unique_other":
                    # Check if file is unique across projects
                    query = ("with fileinfo as (select * from files where file_id = %(file_id)s) "
                                " SELECT f.file_id, fol.project_folder, fol.project_id "
                                " FROM files f, folders fol, fileinfo finfo " 
                                " WHERE f.folder_id = fol.folder_id AND "
                                " f.file_id != %(file_id)s AND f.folder_id != %(folder_id)s AND "
                                " f.folder_id NOT IN (SELECT folder_id from folders where project_id = %(project_id)s) and "
                                "  f.file_name = finfo.file_name")
                    res = run_query(query, {'file_id': file_id, 
                                     'folder_id': folder_id, 'project_id': project_id})
                    if len(res) == 0:
                        check_results = 0
                        check_info = "File not found in the project"
                    elif len(res) == 1:
                        check_results = 1
                        conflict_folder = "{} ({})".format(res[0]['project_folder'], res[0]['project_id'])
                        check_info = "File with the same name in folder: {}".format(conflict_folder)
                    else:
                        check_results = 1
                        conflict_folder = []
                        for row in res:
                            conflict_folder.append("{} ({})".format(row['project_folder'], row['project_id']))
                        conflict_folder = ', '.join(conflict_folder)
                        check_info = "Files with the same name in another project in: {}".format(conflict_folder)
                    query = ("INSERT INTO files_checks "
                        " (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                        "VALUES (%(file_id)s, %(folder_id)s, 'unique_other', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                        " ON DUPLICATE KEY UPDATE"
                        " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                    res = query_database_insert(query, {'file_id': file_id, 
                                                 'folder_id': folder_id, 'check_results': check_results, 
                                                 'check_info': check_info})
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
                        res = run_query(query, {'project_id': project_id,})
                        if len(res) == 0:
                            check_results = 1
                            check_info = "Query for filename not found"
                        else:
                            query = res[0]['settings_details']
                            res = run_query(query, {'file_id': file_id,})
                            logger.info(res)
                            # Get results for file query
                            check_results = res[0]['result']
                            check_info = res[0]['info']
                            if str(check_results) == "1":
                                logger.info(f"Filename check failed {file_id}. Checking if JPCA.")
                                # Hard-coded check for RefID for JPCA from ASpace
                                refid = res[0]['refid']
                                query = (f"SELECT distinct project_id from folders where folder_id in (select folder_id from files where file_id = {file_id})")
                                proj_res = run_query(query)
                                projid = str(proj_res[0]['project_id'])
                                logger.info(f"Project_id: {projid}.")
                                if projid == "220" or projid == "248":
                                    # JPCA
                                    # Login to ASpace
                                    logger.info("Special process for JPCA.")
                                    params = {"password": settings.aspace_api_password}
                                    r = requests.post("{}/users/{}/login".format(settings.aspace_api, settings.aspace_api_username), params=params)
                                    logger.info(f"ASpace r.status_code: {r.status_code}")
                                    if r.status_code == 200:
                                        logger.info("Success! Was able to get token")
                                        response_json = json.loads(r.content.decode('utf-8'))
                                        session_token = response_json['session']
                                        Headers = {"X-ArchivesSpace-Session": session_token}
                                        r = requests.get(f"{settings.aspace_api}/repositories/2/find_by_id/archival_objects?ref_id[]={refid};resolve[]=archival_objects", headers=Headers)
                                        refid_exists = json.loads(r.text.encode('utf-8'))
                                        if len(refid_exists['archival_objects']) != 0:
                                            if refid_exists['archival_objects'][0]['_resolved']['ref_id'] == refid:
                                                query = ("insert into jpc_aspace_data (refid, table_id, resource_id, archive_box, archive_type, archive_folder, unit_title) with data as (select distinct SUBSTRING_INDEX(file_name, '_', 1) as refid from files where file_id = %(file_id)s) (select refid, uuid_v4s(), 'a', 'a', 'a', 'a', 'a' from data)")
                                                logger.info(query)
                                                res = query_database_insert(query, {'file_id': file_id})
                                                logger.info("Inserted")
                                                check_results = 0
                                                check_info = refid
                                    else:
                                        logger.error("\n There was an error when loggin into ASpace: {}".format(r.reason))
                    if transcription == 1:
                        query = (
                            "INSERT INTO transcription_files_checks (file_transcription_id, file_check, check_results, check_info, updated_at) "
                            " VALUES (%(file_id)s, %(file_check)s, %(check_results)s, %(check_info)s, CURRENT_TIME) "
                            " ON DUPLICATE KEY UPDATE "
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query,
                                            {'file_id': file_id, 'file_check': file_check,
                                                'check_results': check_results, 'check_info': check_info})
                    else:
                        query = (
                        "INSERT INTO files_checks (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                        " VALUES (%(file_id)s, %(folder_id)s, %(file_check)s, %(check_results)s, %(check_info)s, CURRENT_TIME) "
                        " ON DUPLICATE KEY UPDATE "
                        " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query,
                                            {'file_id': file_id, 'folder_id': folder_id, 'file_check': file_check,
                                                    'check_results': check_results, 'check_info': check_info})
                    logger.info(res)
                elif query_property == "filemd5":
                    filetype = request.form.get("filetype")
                    folder_id = request.form.get("folder_id")
                    # Check that the md5 doesn't exist
                    if transcription == 1:
                        query = (f"SELECT file_uid as file_id from file_md5 WHERE md5 = %(value)s and file_uid != %(file_id)s")
                    else:
                        query = (f"SELECT file_id from file_md5 WHERE md5 = %(value)s and file_id != %(file_id)s")
                    res = run_query(query, {'file_id': file_id, 'value': query_value})
                    if filetype == "tif":
                        file_check = "md5"
                    else:
                        file_check = "md5_raw"
                    if len(res) == 0:
                        check_results = 0
                        check_info = "Unique MD5 hash"
                        # Check if exists
                        if transcription == 1:
                            query = (f"SELECT file_uid as file_id from file_md5 WHERE file_uid = %(file_id)s")
                        else:
                            query = (f"SELECT file_id from file_md5 WHERE file_id = %(file_id)s")
                        res = run_query(query, {'file_id': file_id})
                        if len(res) != 0:
                            if transcription == 1:
                                query = (f"DELETE from file_md5 WHERE file_uid = %(file_id)s")
                            else:
                                query = (f"DELETE from file_md5 WHERE file_id = %(file_id)s")
                            res = run_query(query, {'file_id': file_id})
                        query = (f"INSERT INTO file_md5 ({fileid}, filetype, md5) "
                            " VALUES (%(file_id)s, %(filetype)s, %(value)s)")
                        res = query_database_insert(query, {'file_id': file_id, 'filetype': filetype, 'value': query_value})
                    else:
                        check_results = 1
                        check_info = "MD5 hash found"
                        # Check if exists
                        if transcription == 1:
                            query = (f"SELECT file_uid as file_id from file_md5 WHERE file_uid = %(file_id)s")
                        else:
                            query = (f"SELECT file_id from file_md5 WHERE file_id = %(file_id)s")
                        res = run_query(query, {'file_id': file_id})
                        if len(res) != 0:
                            if transcription == 1:
                                query = (f"DELETE from file_md5 WHERE file_uid = %(file_id)s")
                            else:
                                query = (f"DELETE from file_md5 WHERE file_id = %(file_id)s")
                            res = run_query(query, {'file_id': file_id})
                        query = (f"INSERT INTO file_md5 ({fileid}, filetype, md5) VALUES (%(file_id)s, %(filetype)s, %(value)s)")
                        res = query_database_insert(query,
                                            {'file_id': file_id, 'filetype': filetype, 'value': query_value})
                    if transcription == 1:
                        query = ("INSERT INTO transcription_files_checks "
                            " (file_transcription_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(file_check)s, %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query, {'file_id': file_id, 'file_check': file_check, 
                                                    'check_results': check_results, 'check_info': check_info})
                    else:
                        query = ("INSERT INTO files_checks "
                            " (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(folder_id)s, %(file_check)s, %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query, {'file_id': file_id, 'file_check': file_check, 
                                                    'folder_id': folder_id, 'check_results': check_results, 
                                                    'check_info': check_info})
                elif query_property == "exif":
                    filetype = request.form.get("filetype")
                    data_json = json.loads(query_value)
                    # exif_data = []
                    if transcription != 1:
                        res = run_query(f"delete from files_exif where {fileid} = %(file_id)s;", {'file_id': file_id}, return_val=False)
                        query = (f"INSERT INTO files_exif ({fileid}, filetype, taggroup, tag, tagid, value) "
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
                                res = query_database_insert(query, row_data)
                            # Remove directory entries that reveal system paths
                            res = run_query(f"delete from files_exif where taggroup = 'System' and tag = 'Directory' and {fileid} = %(file_id)s;", 
                                            {'file_id': file_id}, return_val=False)
                elif query_property == "delete":
                    if transcription == 1:
                        query = ("DELETE FROM transcription_files WHERE file_transcription_id = %(file_id)s")
                    else:
                        query = ("DELETE FROM files WHERE file_id = %(file_id)s")
                    res = run_query(query, {'file_id': file_id}, return_val=False)
                else:
                    return jsonify({'error': 'Invalid value for property: {}'.format(query_property)}), 400
                return jsonify({"result": True})
            else:
                return jsonify({'error': 'Invalid value for type: {}'.format(query_type)}), 400
        else:
            return jsonify({'error': 'Missing args'}), 400



# ok
@app.route('/new/<project_alias>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_new_folder(project_alias=None):
    """Update a project properties."""
    # Check api_key
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(api_key, url='/projects/', params=project_alias)
    if valid_api_key == False:
        return jsonify({'error': 'Forbidden'}), 403
    else:
        if is_admin != True:
            return jsonify({'error': 'Forbidden'}), 403
        else:
            # Get project_id
            results = run_query("SELECT project_id, transcription from projects WHERE project_alias = %(project_alias)s",
                                     {'project_alias': project_alias})
            project_id = results[0]['project_id']
            transcription = results[0]['transcription']
            # New folder info
            query_type = request.form.get("type")
            if query_type is not None:
                if query_type == "folder":
                    folder = request.form.get("folder")
                    folder_path = request.form.get("folder_path")
                    project_id = request.form.get("project_id")
                    folder_date = request.form.get("folder_date")
                    folder_uid = str(uuid.uuid4())
                    if folder is not None and folder_path is not None:
                        if transcription == 1:
                            query = ("INSERT INTO transcription_folders (folder_transcription_id, folder, folder_path, status, project_id, date, previews) "
                                    " VALUES (%(folder_id)s, %(folder)s, %(folder_path)s, 1, %(project_id)s, %(folder_date)s, 1)")
                            data = query_database_insert(query, {'folder_id': folder_uid, 'folder': folder, 'folder_path': folder_path,
                                                                'project_id': project_id, 'folder_date': folder_date})
                            data = run_query("SELECT * FROM transcription_folders WHERE folder_transcription_id = %(folder_transcription_id)s",
                                              {'folder_transcription_id': folder_uid})
                        else:
                            query = ("INSERT INTO folders (folder_uid, project_folder, folder_path, status, project_id, date, previews) "
                                    " VALUES (%(folder_uid)s, %(folder)s, %(folder_path)s, 1, %(project_id)s, %(folder_date)s, 1)")
                            data = query_database_insert(query, {'folder_uid': folder_uid, 'folder': folder, 'folder_path': folder_path,
                                                                'project_id': project_id, 'folder_date': folder_date})
                            data = run_query("SELECT * FROM folders WHERE project_folder = %(project_folder)s AND folder_path = %(folder_path)s AND project_id = %(project_id)s",
                                                {'project_folder': folder, 'folder_path': folder_path, 'project_id': project_id})
                        return jsonify({"result": data})
                    else:
                        return jsonify({"result": False}), 400
                elif query_type == "file":
                    filename = request.form.get("filename")
                    timestamp = request.form.get("timestamp")
                    folder_id = request.form.get("folder_id")
                    filetype = request.form.get("filetype")
                    file_uid = str(uuid.uuid4())
                    if filename is not None and timestamp is not None and folder_id is not None:
                        if transcription == 1:
                            query = ("INSERT INTO transcription_files (file_transcription_id, folder_transcription_id, file_name, file_timestamp, file_ext) "
                                 "  VALUES (%(file_uid)s, %(folder_id)s, %(filename)s, %(timestamp)s, %(file_ext)s)")
                            data = query_database_insert(query, {'file_uid': file_uid, 'folder_id': folder_id, 'filename': filename,
                                                             'timestamp': timestamp, 'file_ext': filetype})
                        else:
                            query = ("INSERT INTO files (file_uid, folder_id, file_name, file_timestamp, uid, file_ext) "
                                 "  VALUES (%(file_uid)s, %(folder_id)s, %(filename)s, %(timestamp)s, uuid_v4s(), %(file_ext)s)")
                            data = query_database_insert(query, {'file_uid': file_uid, 'folder_id': folder_id, 'filename': filename,
                                                             'timestamp': timestamp, 'file_ext': filetype})
                        logger.debug("new_file:{}".format(data))
                        if transcription == 1:
                            file_id = file_uid
                        else:
                            query = ("SELECT file_id FROM files WHERE folder_id = %(folder_id)s AND file_name = %(filename)s")
                            file_info = run_query(query, {'folder_id': folder_id, 'filename': filename})
                            file_id = file_info[0]['file_id']
                            # file_uid = file_info[0]['uid']
                        # Check for unique file
                        if transcription == 1:
                            query = ("SELECT f.file_transcription_id as file_id, fol.folder as project_folder FROM transcription_files f, transcription_folders fol "
                                    " WHERE f.folder_transcription_id = fol.folder_transcription_id AND f.file_name = %(filename)s AND f.folder_transcription_id != %(folder_id)s"
                                    " AND f.folder_transcription_id IN (SELECT folder_transcription_id from transcription_folders where project_id = %(project_id)s)")
                        else:
                            query = ("SELECT f.file_id, fol.project_folder FROM files f, folders fol "
                                    " WHERE f.folder_id = fol.folder_id AND f.file_name = %(filename)s AND f.folder_id != %(folder_id)s"
                                    " AND f.folder_id IN (SELECT folder_id from folders where project_id = %(project_id)s)")
                        res = run_query(query, {'filename': filename, 'folder_id': folder_id, 'project_id': project_id})
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
                        if transcription == 1:
                            query = ("INSERT INTO transcription_files_checks (file_transcription_id, file_check, check_results, check_info, updated_at) "
                                "VALUES (%(file_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                                " ON DUPLICATE KEY UPDATE"
                                " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                            res = query_database_insert(query, {'file_id': file_id, 'check_results': check_results, 'check_info': check_info, 'uid': file_uid})
                            query = ("SELECT file_transcription_id as file_id FROM transcription_files WHERE file_transcription_id = %(file_id)s")
                        else:
                            query = ("INSERT INTO files_checks (file_id, uid, folder_id, file_check, check_results, check_info, updated_at) "
                                "VALUES (%(file_id)s, %(uid)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                                " ON DUPLICATE KEY UPDATE"
                                " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                            res = query_database_insert(query,
                                                        {'file_id': file_id, 'folder_id': folder_id,
                                                        'check_results': check_results, 'check_info': check_info, 'uid': file_uid})
                            query = ("SELECT * FROM files WHERE file_id = %(file_id)s")
                        data = run_query(query, {'file_id': file_id})
                        return jsonify({"result": data})
                    else:
                        return jsonify({'error': 'Missing args'}), 400
                elif query_type == "filesize":
                    file_id = request.form.get("file_id")
                    filetype = request.form.get("filetype")
                    filesize = request.form.get("filesize")
                    if file_id is not None and filetype is not None and filesize is not None:
                        if transcription == 1:
                            query = ("UPDATE transcription_files SET file_size = %(filesize)s where file_transcription_id = %(file_id)s")
                            data = query_database_insert(query, {'file_id': file_id, 'filesize': filesize})
                        else:
                            query = ("INSERT INTO files_size (file_id, filetype, filesize) "
                                    " VALUES (%(file_id)s, %(filetype)s, %(filesize)s) ON DUPLICATE KEY UPDATE "
                                    " filesize = %(filesize)s")
                            data = query_database_insert(query,
                                                        {'file_id': file_id, 'filetype': filetype, 'filesize': filesize})
                        return jsonify({"result": data})
                    else:
                        return jsonify({"result": False}), 400
                else:
                    return jsonify({"result": False}), 400
            else:
                return jsonify({"result": False}), 400


@app.route('/folders/<folder_id>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_details(folder_id=None):
    """Get the details of a folder and the list of files."""
    if folder_id is None:
        return jsonify({'error': 'folder_id is missing'}), 400
    try:
        folder_id = int(folder_id)
        transcription = 0
    except:
        try:
            # Allow for UUIDs
            folder_id = uuid.UUID(folder_id, version=4)
            folder_id = str(folder_id)
            transcription = 1
        except:
            return jsonify({'error': 'folder_id value not valid'}), 400

    # Check api_key
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(api_key, url='/api/folders/', params="folder_id={}".format(folder_id))
    if valid_api_key == False:
        return jsonify({'error': 'Forbidden'}), 403
    if transcription == 1:
        data = run_query(("SELECT f.folder_transcription_id as folder_id, f.project_id, f.folder, "
                           "   p.project_alias, f.status, f.previews, "
                           "   DATE_FORMAT(f.date, '%Y-%m-%d') as folder_date, "
                           "   f.file_errors, f.error_info, "
                            " CASE WHEN f.delivered_to_dams = 0 THEN 'Completed' "
                              "              WHEN f.delivered_to_dams = 1 THEN 'Ready for DAMS' "
                              "              WHEN f.delivered_to_dams = 9 THEN 'Pending' END as delivered_to_dams, "
                           " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                              "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                              "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                              "          'QC Pending') as qc_status "
                        " FROM transcription_folders f "
                     " LEFT JOIN qc_folders qcf ON (f.folder_transcription_id = qcf.folder_uid), projects p "
                      " WHERE f.folder_transcription_id = %(folder_id)s and f.project_id = p.project_id"), {'folder_id': folder_id})
    else:
        data = run_query(("SELECT f.folder_id, f.project_id, f.project_folder as folder, "
                           "   p.project_alias, f.status, f.previews, "
                           "   DATE_FORMAT(f.date, '%Y-%m-%d') as folder_date, "
                           "   f.file_errors, f.error_info, "
                            " CASE WHEN f.delivered_to_dams = 0 THEN 'Completed' "
                              "              WHEN f.delivered_to_dams = 1 THEN 'Ready for DAMS' "
                              "              WHEN f.delivered_to_dams = 9 THEN 'Pending' END as delivered_to_dams, "
                           " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                              "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                              "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                              "          'QC Pending') as qc_status "
                        " FROM folders f "
                     " LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id), projects p "
                      " WHERE f.folder_id = %(folder_id)s and f.project_id = p.project_id"), {'folder_id': folder_id})
    
    if len(data) == 1:
        project_id = data[0]['project_id']
        api_key = request.form.get("api_key")
        logger.info("api_key: {}".format(api_key))
        filechecks_list_temp = run_query(("SELECT settings_value as file_check FROM projects_settings "
                " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
                    {'project_id': project_id})
        filechecks_list = []
        for fcheck in filechecks_list_temp:
            filechecks_list.append(fcheck['file_check'])
        if transcription == 1:
            query = (
                "SELECT f.file_transcription_id as file_id, f.file_name, DATE_FORMAT(f.file_timestamp, '%Y-%m-%d %H:%i:%S') as file_timestamp, "
                " f.dams_uan, f.preview_image, DATE_FORMAT(f.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at, "
                " DATE_FORMAT(f.created_at, '%Y-%m-%d %H:%i:%S') AS created_at, m.md5 as tif_md5 "
                " FROM transcription_files f LEFT JOIN file_md5 m ON (f.file_transcription_id = m.file_uid) WHERE f.folder_transcription_id = %(folder_id)s")
        else:
            query = (
                "SELECT f.file_id, f.file_name, DATE_FORMAT(f.file_timestamp, '%Y-%m-%d %H:%i:%S') as file_timestamp, "
                " f.dams_uan, f.preview_image, DATE_FORMAT(f.updated_at, '%Y-%m-%d %H:%i:%S') as updated_at, "
                " DATE_FORMAT(f.created_at, '%Y-%m-%d %H:%i:%S') AS created_at, m.md5 as tif_md5 "
                " FROM files f LEFT JOIN file_md5 m ON (f.file_id = m.file_id AND lower(m.filetype)='tif') WHERE f.folder_id = %(folder_id)s")
        files_list = run_query(query, {'folder_id': folder_id})
        folder_files_df = pd.DataFrame(files_list)
        for fcheck in filechecks_list:
            logger.info("fcheck: {}".format(fcheck))
            if transcription == 1:
                list_files = pd.DataFrame(run_query(("SELECT f.file_transcription_id as file_id, "
                                                    "   CASE WHEN check_results = 0 THEN 'OK' "
                                                    "       WHEN check_results = 9 THEN 'Pending' "
                                                    "       WHEN check_results = 1 THEN 'Failed' "
                                                    "       ELSE 'Pending' END as {fcheck} "
                                                    " FROM transcription_files f LEFT JOIN transcription_files_checks c ON (f.file_transcription_id=c.file_transcription_id AND c.file_check = %(file_check)s) "
                                                    "  where f.file_transcription_id in (select file_transcription_id from transcription_files where folder_transcription_id = %(folder_id)s)").format(fcheck=fcheck),
                                                {'file_check': fcheck, 'folder_id': folder_id}))
            else:
                list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                    "   CASE WHEN check_results = 0 THEN 'OK' "
                                                    "       WHEN check_results = 9 THEN 'Pending' "
                                                    "       WHEN check_results = 1 THEN 'Failed' "
                                                    "       ELSE 'Pending' END as {fcheck} "
                                                    " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                    "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                {'file_check': fcheck, 'folder_id': folder_id}))
            logger.info("list_files.size: {}".format(list_files.shape[0]))
            if list_files.shape[0] > 0:
                folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
        files = folder_files_df
        data[0]['files'] = files.to_dict('records')
        return jsonify(data[0])
    else:
        return jsonify({'error': 'Folder not found'}), 404


@app.route('/files/<int:file_id>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_file_details(file_id=None):
    """Get the details of a file."""
    if file_id is None:
        return jsonify({'error': 'file_id is missing'}), 400
    # Check api_key
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(api_key, url='/files/', params="file_id={}".format(file_id))
    if valid_api_key == False:
        return jsonify({'error': 'Forbidden'}), 403
    file_id, file_uid = check_file_id(file_id)
    if file_id is None:
        return jsonify({'error': 'File not found'}), 404
    else:
        data = run_query(("SELECT file_id, folder_id, file_name, "
                            "   dams_uan, preview_image, DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%S') as updated_at "
                            " FROM files WHERE file_id = %(file_id)s"),
                            {'file_id': file_id})
        if len(data) == 1:
            data = data[0]
            filechecks = run_query(
                ("WITH data AS (SELECT settings_value as file_check, %(file_id)s as file_id FROM projects_settings " 
                    " WHERE project_setting = 'project_checks' and project_id IN (SELECT project_id FROM folders WHERE folder_id in (SElect folder_id from files where file_id = %(file_id)s ))) "
                    " SELECT f.check_info, CASE WHEN f.check_results IS NULL THEN 'Pending' WHEN f.check_results = 9 THEN 'Pending' WHEN f.check_results = 0 THEN 'OK' WHEN f.check_results = 1 THEN 'Failed' END as check_results, d.file_check, DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%S') as updated_at " 
                    " FROM data d LEFT JOIN files_checks f ON (d.file_id = f.file_id and d.file_check = f.file_check)"),
                {'file_id': file_id})
            data['file_checks'] = filechecks
            file_exif = run_query(
                ("SELECT tag, value, filetype, tagid, taggroup "
                " FROM files_exif WHERE file_id = %(file_id)s"),
                {'file_id': file_id})
            data['exif'] = file_exif
            file_md5 = run_query(("SELECT filetype, md5 "
                                    "FROM file_md5 WHERE file_id = %(file_id)s"),
                                    {'file_id': file_id})
            data['md5_hashes'] = file_md5
            file_links = run_query(
                ("SELECT link_name, link_url, link_notes "
                "FROM files_links WHERE file_id = %(file_id)s"),
                {'file_id': file_id})
            data['links'] = file_links
            file_post = run_query(
                ("SELECT post_step, post_results, post_info, DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%S') as updated_at, "
                 " CASE WHEN post_results IS NULL THEN 'Pending' WHEN post_results = 9 THEN 'Pending' WHEN post_results = 0 THEN 'OK' WHEN post_results = 1 THEN 'Failed' END as post_results "
                "FROM file_postprocessing WHERE file_id = %(file_id)s"),
                {'file_id': file_id})
            data['file_postprocessing'] = file_post
            return jsonify(data)
        else:
            return jsonify({'error': 'file_id not found'}), 404



@app.route('/reports/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
@app.route('/reports/<report_id>/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_report(report_id=None):
    """Get the data from a project report."""
    if report_id is None:
        return jsonify({'error': 'report_id is missing'}), 400
    # Check api_key
    api_key = request.form.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(api_key, url='/reports/', params="report_id={}".format(report_id))
    if valid_api_key == False:
        return jsonify({'error': 'Forbidden'}), 403
    else:
        data = run_query("SELECT * FROM data_reports WHERE report_id = %(report_id)s",
                               {'report_id': report_id})
        if len(data) == 0:
            data = run_query("SELECT * FROM data_reports WHERE report_alias = %(report_id)s",
                                   {'report_id': report_id})
            if len(data) == 0:
                return jsonify({'error': 'Report not found'}), 404
        return jsonify(data)



#####################################
if __name__ == '__main__':
    app.run(threaded=False, debug=True)
    
