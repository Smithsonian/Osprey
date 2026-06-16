"""API routes (auto-split from legacy app.py)."""
import json
import re
import uuid

import pandas as pd
import requests
from flask import current_app, jsonify, request

from cache import cache
from logger import logger

from api import api_bp
from api.auth import check_file_id, validate_api_key
from osprey.db import run_query

@api_bp.route('/files/<int:file_id>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
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

