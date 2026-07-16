"""Project read API routes."""

from flask import jsonify, request

from cache import cache
from logger import api_logger as logger

from api import api_bp
from api.auth import validate_api_key
from osprey.db import run_query
from osprey.services import folder_stats as folder_stats_service
from osprey.services import folders as folder_service
from osprey.services import projects as project_service


@cache.memoize()
@api_bp.route('/projects/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_projects():
    """Get the list of projects."""
    section = request.form.get("section")
    logger.info("api_get_projects called | section={}".format(section))
    projects_data = project_service.list_projects(section)
    last_update = run_query(
        "SELECT date_format(MAX(updated_at), '%Y-%m-%d') AS updated_at FROM projects_stats"
    )
    return jsonify({"projects": projects_data, "last_update": last_update[0]['updated_at']})


@cache.memoize()
@api_bp.route('/projects/<project_alias>', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_project_details(project_alias=None):
    """Get project details and folder list by project_alias (used by the dashboard sidebar)."""
    logger.info("api_get_project_details called | project_alias={}".format(project_alias))
    rows = project_service.get_project_row(project_alias)
    if len(rows) == 1:
        return jsonify(project_service.enrich_project_details(rows[0]))
    logger.warning("api_get_project_details: project not found | project_alias={}".format(project_alias))
    return jsonify({'error': 'Project was not found'}), 404


@cache.memoize()
@api_bp.route('/projects/<project_alias>/files', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_project_files(project_alias=None):
    """Get the list of files of a project by specifying the project_alias."""
    logger.info("api_get_project_files called | project_alias={}".format(project_alias))
    data = project_service.list_project_files(project_alias)
    if len(data) == 0:
        logger.warning("api_get_project_files: no files found | project_alias={}".format(project_alias))
        return jsonify({'result': False}), 404
    return jsonify(data)


@api_bp.route(
    '/projects/<project_alias>/recalculate-stats',
    methods=['POST'],
    strict_slashes=False,
    provide_automatic_options=False,
)
def api_recalculate_project_folder_stats(project_alias=None):
    """Recalculate stats for all folders in a project (admin api_key required).

    Optional form/query param ``status`` limits recalculation to folders with
    that status (e.g. ``0`` for active only). Omit to process all folders.
    """
    api_key = request.values.get("api_key")
    if api_key is None or api_key == "":
        return jsonify({'error': 'api_key is missing'}), 400
    valid_api_key, is_admin = validate_api_key(
        api_key,
        url='/projects/{}/recalculate-stats'.format(project_alias),
        params="project_alias={}".format(project_alias),
    )
    if not valid_api_key or not is_admin:
        return jsonify({'error': 'Forbidden'}), 403

    rows = project_service.get_project_row(project_alias)
    if len(rows) != 1:
        return jsonify({'error': 'Project was not found'}), 404

    project_id = rows[0]['project_id']
    transcription = rows[0]['transcription']

    status_raw = request.values.get("status")
    status = None
    if status_raw is not None and status_raw != "":
        try:
            status = int(status_raw)
        except (TypeError, ValueError):
            return jsonify({'error': 'status must be an integer'}), 400

    folder_rows = folder_service.list_folder_ids_for_project(
        project_id, transcription, status=status,
    )
    logger.info(
        "api_recalculate_project_folder_stats | project_alias={} | status={} | folders={}".format(
            project_alias, status, len(folder_rows),
        )
    )

    results = []
    for row in folder_rows:
        results.append(
            folder_stats_service.recalculate_folder_stats(
                project_id, row['folder_id'], transcription,
            )
        )

    try:
        folder_stats_service.recalculate_project_stats(project_id, transcription)
    except ValueError as err:
        return jsonify({'error': str(err)}), 400

    cache.delete_memoized(api_get_project_details, project_alias)

    return jsonify({
        'result': True,
        'project_alias': project_alias,
        'folders_processed': len(results),
        'folders': results,
    })
