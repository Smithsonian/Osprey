"""Project read API routes."""

from flask import jsonify, request

from cache import cache
from logger import api_logger as logger

from api import api_bp
from osprey.db import run_query
from osprey.services import projects as project_service


@cache.memoize()
@api_bp.route('/projects/', methods=['POST', 'GET'], strict_slashes=False, provide_automatic_options=False)
def api_get_projects():
    """Get the list of projects."""
    section = request.form.get("section")
    logger.info("api_get_projects called | section={}".format(section))
    projects_data = project_service.list_projects(section)
    last_update = run_query(
        "SELECT date_format(MAX(updated_at), '%d-%m-%Y') AS updated_at FROM projects_stats"
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
