"""API routes (auto-split from legacy app.py)."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pandas as pd
from flask import current_app, jsonify, request

import settings
from cache import cache
from logger import api_logger as logger

from api import api_bp
from api.auth import validate_api_key
from osprey.db import query_database_insert, run_query
from osprey.services import folder_stats as folder_stats_service
from osprey.services.file_checks import (
    filename_check_enabled,
    run_filename_check,
)


def _parse_preview_type(value):
    """Return (preview_type, badge_text, badge_css) or None if invalid."""
    preview_type = str(value).lower()
    if preview_type not in ('dzi', 'iiif'):
        return None
    badge_text = 'DZI' if preview_type == 'dzi' else 'IIIF'
    badge_css = 'bg-info' if preview_type == 'dzi' else 'bg-primary'
    return preview_type, badge_text, badge_css


def _upsert_preview_type_badge(fid, folder_id, badge_text, badge_css):
    query = (
        f"INSERT INTO folders_badges ({fid}, badge_type, badge_css, badge_text, updated_at) "
        "VALUES (%(folder_id)s, 'preview_type', %(badge_css)s, %(badge_text)s, CURRENT_TIMESTAMP) "
        "ON DUPLICATE KEY UPDATE badge_text = %(badge_text)s, badge_css = %(badge_css)s, updated_at = CURRENT_TIMESTAMP"
    )
    return query_database_insert(
        query,
        {'folder_id': folder_id, 'badge_text': badge_text, 'badge_css': badge_css},
    )

@api_bp.route('/update/<project_alias>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
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
                        folder_stats_service.recalculate_folder_stats(
                            project_id, folder_id, transcription,
                        )
                        try:
                            folder_stats_service.recalculate_project_stats(
                                project_id, transcription,
                            )
                        except ValueError as err:
                            return jsonify({'error': str(err)}), 400
                        logger.info(
                            "query: update|{}|{}|folder_stats|{}".format(
                                query_type, query_property, folder_id,
                            )
                        )
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
                        if transcription == 1:
                            query = ("UPDATE transcription_folders SET previews = %(value)s WHERE folder_transcription_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': query_value})
                        else:
                            query = ("UPDATE folders SET previews = %(value)s WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': query_value})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                    elif query_property == "preview_type":
                        parsed = _parse_preview_type(query_value)
                        if parsed is None:
                            return jsonify({'error': 'preview_type must be dzi or iiif'}), 400
                        preview_type, badge_text, badge_css = parsed
                        if transcription == 1:
                            query = ("UPDATE transcription_folders SET preview_type = %(value)s WHERE folder_transcription_id = %(folder_id)s")
                        else:
                            query = ("UPDATE folders SET preview_type = %(value)s WHERE folder_id = %(folder_id)s")
                        res = query_database_insert(query, {'folder_id': folder_id, 'value': preview_type})
                        logger.info("query: update|{}|{}|{}|{}|{}".format(query_type, query_property, query, folder_id, res))
                        res = _upsert_preview_type_badge(fid, folder_id, badge_text, badge_css)
                        logger.info("query: update|{}|{}|badge|{}|{}".format(query_type, query_property, folder_id, res))
                    elif query_property == "qc":
                        query = ("SELECT * FROM qc_folders WHERE folder_id = %(folder_id)s")
                        folder_qc = run_query(query, {'folder_id': folder_id})
                        if len(folder_qc) == 0:
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
                        if not filename_check_enabled(project_id):
                            check_results = 1
                            check_info = "Query for filename not found"
                        else:
                            res = run_filename_check(file_id, project_id=project_id)
                            logger.info("filename check result for file_id=%s: %s", file_id, res)
                            # Get results for file query
                            check_results = res['result']
                            check_info = res['info']
                            if str(check_results) == "1":
                                logger.info(f"Filename check failed {file_id}. Checking if JPCA.")
                                # Hard-coded check for RefID for JPCA from ASpace
                                refid = res['refid']
                                query = (
                                    "SELECT distinct project_id from folders where folder_id in "
                                    "(select folder_id from files where file_id = %(file_id)s)"
                                )
                                proj_res = run_query(query, {'file_id': file_id})
                                projid = str(proj_res[0]['project_id'])
                                logger.info(f"Project_id: {projid}.")
                                if projid == "220" or projid == "248":
                                    # JPCA
                                    # Login to ASpace
                                    logger.info("Special process for JPCA.")
                                    login_params = {"password": getattr(settings, 'aspace_api_password', None)}
                                    login_url = "{}/users/{}/login?{}".format(
                                        getattr(settings, 'aspace_api', None),
                                        getattr(settings, 'aspace_api_username', None),
                                        urllib.parse.urlencode(login_params),
                                    )
                                    try:
                                        with urllib.request.urlopen(urllib.request.Request(login_url, method="POST")) as resp:
                                            status_code = resp.status
                                            reason = resp.reason
                                            response_json = json.loads(resp.read().decode('utf-8'))
                                    except urllib.error.HTTPError as err:
                                        status_code = err.code
                                        reason = err.reason
                                        response_json = None
                                    logger.info(f"ASpace r.status_code: {status_code}")
                                    if status_code == 200:
                                        logger.info("Success! Was able to get token")
                                        session_token = response_json['session']
                                        Headers = {"X-ArchivesSpace-Session": session_token}
                                        lookup_url = f"{getattr(settings, 'aspace_api', None)}/repositories/2/find_by_id/archival_objects?ref_id[]={refid};resolve[]=archival_objects"
                                        with urllib.request.urlopen(urllib.request.Request(lookup_url, headers=Headers)) as resp:
                                            refid_exists = json.loads(resp.read().decode('utf-8'))
                                        if len(refid_exists['archival_objects']) != 0:
                                            if refid_exists['archival_objects'][0]['_resolved']['ref_id'] == refid:
                                                query = ("insert into jpc_aspace_data (refid, table_id, resource_id, archive_box, archive_type, archive_folder, unit_title) with data as (select distinct SUBSTRING_INDEX(file_name, '_', 1) as refid from files where file_id = %(file_id)s) (select refid, uuid_v4s(), 'a', 'a', 'a', 'a', 'a' from data)")
                                                logger.info(query)
                                                res = query_database_insert(query, {'file_id': file_id})
                                                logger.info("Inserted")
                                                check_results = 0
                                                check_info = refid
                                    else:
                                        logger.error("\n There was an error when loggin into ASpace: {}".format(reason))
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
                elif query_property == "filemd5_missing_raw":
                    if transcription == 1:
                        query = ("INSERT INTO transcription_files_checks "
                            " (file_transcription_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, 'md5_raw', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query, {'file_id': file_id, 'file_check': file_check, 
                                                    'check_results': 1, 'check_info': "Missing RAW File"})
                    else:
                        query = ("INSERT INTO files_checks "
                            " (file_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, 'md5_raw', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query, {'file_id': file_id, 'check_results': 1, 
                                                    'check_info': "Missing RAW File"})
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
                                if key.split(':')[0] == "System":
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
@api_bp.route('/new/<project_alias>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
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
                    preview_type_raw = request.form.get("preview_type")
                    folder_uid = str(uuid.uuid4())
                    if folder is not None and folder_path is not None:
                        preview_type = None
                        badge_text = None
                        badge_css = None
                        if preview_type_raw:
                            parsed = _parse_preview_type(preview_type_raw)
                            if parsed is None:
                                return jsonify({'error': 'preview_type must be dzi or iiif'}), 400
                            preview_type, badge_text, badge_css = parsed
                        if transcription == 1:
                            if preview_type:
                                query = ("INSERT INTO transcription_folders (folder_transcription_id, folder, folder_path, status, project_id, date, previews, preview_type) "
                                        " VALUES (%(folder_id)s, %(folder)s, %(folder_path)s, 1, %(project_id)s, %(folder_date)s, 1, %(preview_type)s)")
                                data = query_database_insert(query, {'folder_id': folder_uid, 'folder': folder, 'folder_path': folder_path,
                                                                    'project_id': project_id, 'folder_date': folder_date, 'preview_type': preview_type})
                            else:
                                query = ("INSERT INTO transcription_folders (folder_transcription_id, folder, folder_path, status, project_id, date, previews) "
                                        " VALUES (%(folder_id)s, %(folder)s, %(folder_path)s, 1, %(project_id)s, %(folder_date)s, 1)")
                                data = query_database_insert(query, {'folder_id': folder_uid, 'folder': folder, 'folder_path': folder_path,
                                                                    'project_id': project_id, 'folder_date': folder_date})
                            if preview_type:
                                _upsert_preview_type_badge('folder_uid', folder_uid, badge_text, badge_css)
                            data = run_query("SELECT * FROM transcription_folders WHERE folder_transcription_id = %(folder_transcription_id)s",
                                              {'folder_transcription_id': folder_uid})
                        else:
                            if preview_type:
                                query = ("INSERT INTO folders (folder_uid, project_folder, folder_path, status, project_id, date, previews, preview_type) "
                                        " VALUES (%(folder_uid)s, %(folder)s, %(folder_path)s, 1, %(project_id)s, %(folder_date)s, 1, %(preview_type)s)")
                                data = query_database_insert(query, {'folder_uid': folder_uid, 'folder': folder, 'folder_path': folder_path,
                                                                    'project_id': project_id, 'folder_date': folder_date, 'preview_type': preview_type})
                            else:
                                query = ("INSERT INTO folders (folder_uid, project_folder, folder_path, status, project_id, date, previews) "
                                        " VALUES (%(folder_uid)s, %(folder)s, %(folder_path)s, 1, %(project_id)s, %(folder_date)s, 1)")
                                data = query_database_insert(query, {'folder_uid': folder_uid, 'folder': folder, 'folder_path': folder_path,
                                                                    'project_id': project_id, 'folder_date': folder_date})
                            data = run_query("SELECT * FROM folders WHERE project_folder = %(project_folder)s AND folder_path = %(folder_path)s AND project_id = %(project_id)s",
                                                {'project_folder': folder, 'folder_path': folder_path, 'project_id': project_id})
                            if preview_type and data:
                                _upsert_preview_type_badge('folder_id', data[0]['folder_id'], badge_text, badge_css)
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
                            # res = query_database_insert(query, {'file_id': file_id, 'check_results': check_results, 'check_info': check_info, 'uid': file_uid})
                            query = ("SELECT file_transcription_id as file_id FROM transcription_files WHERE file_transcription_id = %(file_id)s")
                        else:
                            query = ("INSERT INTO files_checks (file_id, uid, folder_id, file_check, check_results, check_info, updated_at) "
                                "VALUES (%(file_id)s, %(uid)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                                " ON DUPLICATE KEY UPDATE"
                                " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                            # res = query_database_insert(query, {'file_id': file_id, 'folder_id': folder_id, 'check_results': check_results, 'check_info': check_info, 'uid': file_uid})
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

