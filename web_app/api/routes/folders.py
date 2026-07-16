"""Folder read API routes."""

import pandas as pd
from flask import jsonify, request

from api import api_bp
from api.auth import validate_api_key
from osprey.services import folder_details as folder_service


@api_bp.route('/folders/<folder_id>/files', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_files(folder_id=None):
    """Get folder details; each file includes file_checks as an array."""
    payload, status, message = folder_service.get_folder_files_payload(folder_id)
    if payload is None:
        if status == 400:
            return jsonify({'error': message or 'folder_id value not valid'}), 400
        return jsonify({'error': message or 'Folder not found'}), 404
    return jsonify(payload)


@api_bp.route('/folders/<folder_id>/qc', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_qc(folder_id=None):
    """Get folder visual-QC sampling summary."""
    payload, status, message = folder_service.get_folder_qc_payload(folder_id)
    if payload is None:
        if status == 400:
            return jsonify({'error': message or 'folder_id value not valid'}), 400
        return jsonify({'error': message or 'Folder not found'}), 404
    return jsonify(payload)


@api_bp.route('/folders/<folder_id>/transcription_qc', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_transcription_qc(folder_id=None):
    """Get folder transcription-QC sampling summaries by source."""
    payload, status, message = folder_service.get_folder_transcription_qc_payload(folder_id)
    if payload is None:
        if status == 400:
            return jsonify({'error': message or 'folder_id value not valid'}), 400
        return jsonify({'error': message or 'Folder not found'}), 404
    return jsonify(payload)


@api_bp.route('/folders/<folder_id>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_folder_details(folder_id=None):
    """Get the details of a folder and the list of files (flat check columns; requires api_key)."""
    try:
        folder_id, transcription = folder_service.parse_folder_id(folder_id)
    except ValueError as err:
        return jsonify({'error': str(err)}), 400

    api_key = request.values.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(
        api_key, url='/api/folders/', params="folder_id={}".format(folder_id),
    )
    if valid_api_key is False:
        return jsonify({'error': 'Forbidden'}), 403

    data = folder_service.get_folder_details_row(folder_id, transcription)
    if data is None:
        return jsonify({'error': 'Folder not found'}), 404

    project_id = data['project_id']
    filechecks_list = folder_service.list_project_file_checks(project_id)
    files_list = folder_service.list_folder_files_base(folder_id, transcription)
    folder_files_df = pd.DataFrame(files_list)
    if not folder_files_df.empty and filechecks_list:
        folder_files_df = folder_service.attach_checks_flat(
            folder_files_df, folder_id, transcription, filechecks_list,
        )

    payload = dict(data)
    payload.pop('transcription', None)
    payload['files'] = folder_files_df.to_dict('records') if not folder_files_df.empty else []
    return jsonify(payload)
